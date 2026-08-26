from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gsc_contract import file_sha256


MANIFEST_VERSION = 1
STREAM_SPECS = {
    "landing": {
        "default_file": "ga4_organic_landing_pages_90d.csv",
        "dimensions": ["date", "landingPagePlusQueryString", "sessionDefaultChannelGroup"],
        "metrics": ["sessions", "engagedSessions", "conversions", "totalRevenue"],
    },
    "funnel": {
        "default_file": "ga4_organic_funnel_90d.csv",
        "dimensions": ["date", "landingPagePlusQueryString", "eventName"],
        "metrics": ["eventCount"],
        "events": ["add_to_cart", "begin_checkout"],
    },
}


def stream_request(stream_name: str, start_date: str, end_date: str) -> dict:
    spec = STREAM_SPECS[stream_name]
    request = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": spec["dimensions"],
        "metrics": spec["metrics"],
        "channel": "Organic Search",
    }
    if spec.get("events"):
        request["events"] = spec["events"]
    return request


def build_ga4_manifest(
    start_date: str,
    end_date: str,
    stream_paths: dict[str, Path],
    stream_rows: dict[str, list[dict]],
) -> dict:
    streams = {}
    for stream_name in STREAM_SPECS:
        path = stream_paths[stream_name]
        streams[stream_name] = {
            "file": path.name,
            "request": stream_request(stream_name, start_date, end_date),
            "row_count": len(stream_rows[stream_name]),
            "sha256": file_sha256(path),
        }
    return {
        "version": MANIFEST_VERSION,
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "expected_window": {"startDate": start_date, "endDate": end_date},
        "streams": streams,
    }


def write_ga4_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_and_validate_ga4_artifacts(
    manifest_path: Path,
    expected_start: str,
    expected_end: str,
    stream_paths: dict[str, Path],
    frames: dict[str, pd.DataFrame],
) -> tuple[dict, dict[str, pd.DataFrame]]:
    if not manifest_path.exists():
        raise RuntimeError(f"GA4 fetch manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise RuntimeError(f"GA4 fetch manifest is unreadable: {manifest_path}") from error

    if manifest.get("version") != MANIFEST_VERSION or manifest.get("status") != "complete":
        raise RuntimeError("GA4 fetch manifest is not a completed supported manifest")
    expected_window = {"startDate": expected_start, "endDate": expected_end}
    if manifest.get("expected_window") != expected_window:
        raise RuntimeError(
            f"GA4 fetch manifest window mismatch: expected {expected_start}..{expected_end}"
        )

    manifest_streams = manifest.get("streams") or {}
    prepared: dict[str, pd.DataFrame] = {}
    for stream_name in STREAM_SPECS:
        path = stream_paths[stream_name]
        frame = frames[stream_name]
        stream = manifest_streams.get(stream_name) or {}
        if stream.get("request") != stream_request(stream_name, expected_start, expected_end):
            raise RuntimeError(f"GA4 {stream_name} manifest request contract mismatch")
        if stream.get("file") != path.name:
            raise RuntimeError(f"GA4 {stream_name} manifest file mismatch")
        if not path.exists() or stream.get("sha256") != file_sha256(path):
            raise RuntimeError(f"GA4 {stream_name} file does not match its manifest")
        if stream.get("row_count") != len(frame):
            raise RuntimeError(f"GA4 {stream_name} row count does not match its manifest")
        if stream_name == "landing" and frame.empty:
            raise RuntimeError("GA4 landing CSV is empty")
        if not frame.empty and "date" not in frame.columns:
            raise RuntimeError(f"GA4 {stream_name} CSV is missing date")

        current = frame.copy()
        if not current.empty:
            current["date"] = pd.to_datetime(current["date"], errors="coerce").dt.normalize()
            if current["date"].isna().any():
                raise RuntimeError(f"GA4 {stream_name} CSV contains invalid dates")
            outside = ~current["date"].between(
                pd.Timestamp(expected_start), pd.Timestamp(expected_end)
            )
            if outside.any():
                raise RuntimeError(
                    f"GA4 {stream_name} CSV contains dates outside {expected_start}..{expected_end}"
                )
        prepared[stream_name] = current

    return manifest, prepared
