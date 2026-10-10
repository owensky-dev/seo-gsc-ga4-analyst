"""Fetch finalized page-daily GSC data without requiring GA4 configuration."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def default_window(today: date | None = None) -> tuple[date, date]:
    final_day = (today or datetime.now(ZoneInfo("America/Los_Angeles")).date()) - timedelta(days=3)
    first = final_day.replace(day=1)
    start = first.replace(year=first.year - 1)
    return start, final_day


def fetch_day(service, site: str, current: date) -> list[dict]:
    rows = []
    while len(rows) < 50000:
        body = {"startDate": current.isoformat(), "endDate": current.isoformat(),
                "dimensions": ["date", "page"], "type": "web", "aggregationType": "byPage",
                "dataState": "final", "rowLimit": 25000, "startRow": len(rows)}
        result = service.searchanalytics().query(siteUrl=site, body=body).execute(num_retries=3)
        if result.get("responseAggregationType") != "byPage":
            raise RuntimeError("Unexpected GSC aggregation type")
        batch = result.get("rows", [])
        for row in batch:
            if len(row.get("keys", [])) != 2 or row["keys"][0] != current.isoformat():
                raise RuntimeError("Unexpected GSC date/page keys")
            rows.append(dict(zip(["date", "page"], row["keys"]), **{k: row[k] for k in ["clicks", "impressions", "ctr", "position"]}))
        if len(batch) < 25000:
            break
    return rows


def collect(service, site: str, start: date, end: date, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_suffix(".csv.pending")
    days, count = [], 0
    # Final CSV/manifest remain untouched on fetch failure. A partial file is never a success.
    with pending.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "page", "clicks", "impressions", "ctr", "position"])
        writer.writeheader()
        current = start
        while current <= end:
            rows = fetch_day(service, site, current)
            writer.writerows(rows)
            count += len(rows)
            days.append({"date": current.isoformat(), "status": "complete", "rows": len(rows), "capped": len(rows) >= 50000})
            print(f"{current}: {len(rows)} rows", flush=True)
            current += timedelta(days=1)
    manifest = {"version": 1, "kind": "gsc-content-decay", "status": "complete",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "window": {"start": start.isoformat(), "end": end.isoformat()},
                "request": {"dimensions": ["date", "page"], "type": "web", "aggregationType": "byPage", "dataState": "final"},
                "file": output.name, "row_count": count, "sha256": hashlib.sha256(pending.read_bytes()).hexdigest(), "days": days,
                "note": "Complete requests, not guaranteed exhaustive GSC rows. Missing rows are zero only within the returned dataset; capped dates remain incomplete."}
    manifest_path = output.with_suffix(".manifest.json")
    temporary = manifest_path.with_suffix(".json.pending")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(output)
    temporary.replace(manifest_path)
    return manifest_path


def main() -> None:
    from dotenv import load_dotenv
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=date.fromisoformat)
    parser.add_argument("--end-date", type=date.fromisoformat)
    parser.add_argument("--out", type=Path, default=root / "data/raw/gsc_content_decay.csv")
    args = parser.parse_args()
    if bool(args.start_date) != bool(args.end_date):
        parser.error("Provide both --start-date and --end-date")
    start, end = (args.start_date, args.end_date) if args.start_date else default_window()
    today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    if start > end or end > today - timedelta(days=3) or start < today - timedelta(days=480):
        parser.error("Use a historical window within 480 days, ending at least 3 days ago")
    site, key = os.getenv("GSC_SITE_URL"), os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not site or not key:
        parser.error("Set GSC_SITE_URL and GOOGLE_APPLICATION_CREDENTIALS in local .env; GA4 is not required")
    credentials = service_account.Credentials.from_service_account_file(key, scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    service = build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
    manifest = collect(service, site, start, end, args.out)
    print(f"Saved: {args.out}\nManifest: {manifest}\nGSC top rows only; capped days are marked incomplete.")


if __name__ == "__main__":
    main()
