from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import DATA_RAW_DIR, default_gsc_date_range, ensure_dirs, load_settings
from gsc_contract import (
    STREAM_SPECS,
    build_gsc_manifest,
    write_gsc_manifest,
)


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
DETAIL_DIMENSIONS = STREAM_SPECS["detail"]["dimensions"]
SITE_DAILY_DIMENSIONS = STREAM_SPECS["site_daily"]["dimensions"]
PAGE_DAILY_DIMENSIONS = STREAM_SPECS["page_daily"]["dimensions"]
DETAIL_COLUMNS = [
    "date",
    "page",
    "query",
    "country",
    "device",
    "clicks",
    "impressions",
    "ctr",
    "position",
]
SITE_DAILY_COLUMNS = ["date", "clicks", "impressions", "ctr", "position"]
PAGE_DAILY_COLUMNS = ["date", "page", "clicks", "impressions", "ctr", "position"]


def build_search_analytics_body(
    start_date: str,
    end_date: str,
    dimensions: list[str],
    row_limit: int,
    start_row: int,
    aggregation_type: str | None = None,
) -> dict:
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions,
        "type": "web",
        "rowLimit": row_limit,
        "startRow": start_row,
    }
    if aggregation_type:
        body["aggregationType"] = aggregation_type
    return body


def fetch_gsc_rows(
    key_file: str,
    site_url: str,
    start_date: str,
    end_date: str,
    row_limit: int = 25000,
    dimensions: list[str] | None = None,
    aggregation_type: str | None = None,
) -> list[dict]:
    credentials = service_account.Credentials.from_service_account_file(
        key_file,
        scopes=SCOPES,
    )
    service = build("searchconsole", "v1", credentials=credentials, cache_discovery=False)

    rows: list[dict] = []
    start_row = 0
    dimensions = dimensions or DETAIL_DIMENSIONS

    while True:
        body = build_search_analytics_body(
            start_date,
            end_date,
            dimensions,
            row_limit,
            start_row,
            aggregation_type,
        )
        response = (
            service.searchanalytics()
            .query(siteUrl=site_url, body=body)
            .execute()
        )
        batch = response.get("rows", [])
        if not batch:
            break

        for item in batch:
            keys = item.get("keys", [])
            record = {dimension: keys[index] if index < len(keys) else "" for index, dimension in enumerate(dimensions)}
            record.update(
                {
                    "clicks": item.get("clicks", 0),
                    "impressions": item.get("impressions", 0),
                    "ctr": item.get("ctr", 0),
                    "position": item.get("position", 0),
                }
            )
            rows.append(record)

        if len(batch) < row_limit:
            break
        start_row += row_limit

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Google Search Console search performance data.")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--finalized-lag-days", type=int, default=3)
    parser.add_argument("--row-limit", type=int, default=25000)
    parser.add_argument("--out", default=str(DATA_RAW_DIR / "gsc_90d.csv"))
    parser.add_argument("--daily-out", default=str(DATA_RAW_DIR / "gsc_daily_90d.csv"))
    parser.add_argument("--page-daily-out", default=str(DATA_RAW_DIR / "gsc_page_daily_90d.csv"))
    parser.add_argument("--manifest-out", default=str(DATA_RAW_DIR / "gsc_fetch_manifest.json"))
    args = parser.parse_args()

    settings = load_settings()
    ensure_dirs()
    if bool(args.start_date) != bool(args.end_date):
        raise RuntimeError("--start-date and --end-date must be provided together")
    start_date, end_date = (
        (args.start_date, args.end_date)
        if args.start_date
        else default_gsc_date_range(args.days, args.finalized_lag_days)
    )

    rows = fetch_gsc_rows(
        key_file=settings["GOOGLE_APPLICATION_CREDENTIALS"],
        site_url=settings["GSC_SITE_URL"],
        start_date=start_date,
        end_date=end_date,
        row_limit=args.row_limit,
    )
    daily_rows = fetch_gsc_rows(
        key_file=settings["GOOGLE_APPLICATION_CREDENTIALS"],
        site_url=settings["GSC_SITE_URL"],
        start_date=start_date,
        end_date=end_date,
        row_limit=args.row_limit,
        dimensions=SITE_DAILY_DIMENSIONS,
        aggregation_type="byProperty",
    )
    page_daily_rows = fetch_gsc_rows(
        key_file=settings["GOOGLE_APPLICATION_CREDENTIALS"],
        site_url=settings["GSC_SITE_URL"],
        start_date=start_date,
        end_date=end_date,
        row_limit=args.row_limit,
        dimensions=PAGE_DAILY_DIMENSIONS,
        aggregation_type="byPage",
    )
    if not daily_rows:
        raise RuntimeError("GSC site-level daily query returned no rows")
    if not page_daily_rows:
        raise RuntimeError("GSC page-level daily query returned no rows")

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=DETAIL_COLUMNS).to_csv(output_path, index=False)
    daily_output_path = Path(args.daily_out)
    daily_output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(daily_rows, columns=SITE_DAILY_COLUMNS).to_csv(daily_output_path, index=False)
    page_daily_output_path = Path(args.page_daily_out)
    page_daily_output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(page_daily_rows, columns=PAGE_DAILY_COLUMNS).to_csv(
        page_daily_output_path, index=False
    )
    manifest_output_path = Path(args.manifest_out)
    stream_paths = {
        "detail": output_path,
        "site_daily": daily_output_path,
        "page_daily": page_daily_output_path,
    }
    stream_rows = {
        "detail": rows,
        "site_daily": daily_rows,
        "page_daily": page_daily_rows,
    }
    manifest = build_gsc_manifest(
        start_date,
        end_date,
        args.row_limit,
        stream_paths,
        stream_rows,
    )
    write_gsc_manifest(manifest_output_path, manifest)
    print(
        f"GSC detail_rows={len(rows)} site_daily_rows={len(daily_rows)} "
        f"page_daily_rows={len(page_daily_rows)} date_range={start_date}..{end_date} "
        f"out={output_path} daily_out={daily_output_path} "
        f"page_daily_out={page_daily_output_path} manifest_out={manifest_output_path}"
    )


if __name__ == "__main__":
    main()
