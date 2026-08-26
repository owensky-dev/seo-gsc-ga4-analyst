from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import pandas as pd


MANIFEST_VERSION = 1
METRIC_COLUMNS = ["clicks", "impressions", "ctr", "position"]
STREAM_SPECS = {
    "detail": {
        "default_file": "gsc_90d.csv",
        "dimensions": ["date", "page", "query", "country", "device"],
    },
    "site_daily": {
        "default_file": "gsc_daily_90d.csv",
        "dimensions": ["date"],
        "aggregationType": "byProperty",
    },
    "page_daily": {
        "default_file": "gsc_page_daily_90d.csv",
        "dimensions": ["date", "page"],
        "aggregationType": "byPage",
    },
}


def stream_request(
    stream_name: str, start_date: str, end_date: str, row_limit: int
) -> dict:
    spec = STREAM_SPECS[stream_name]
    request = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": spec["dimensions"],
        "type": "web",
        "rowLimit": row_limit,
    }
    if spec.get("aggregationType"):
        request["aggregationType"] = spec["aggregationType"]
    return request


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bytes_sha256(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def read_file_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise RuntimeError(f"{label} is missing or unreadable: {path}") from error


def parse_json_bytes(contents: bytes, label: str) -> dict:
    try:
        payload = json.loads(contents)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError(f"{label} is not valid JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} is not a JSON object")
    return payload


def parse_csv_bytes(contents: bytes, label: str) -> pd.DataFrame:
    try:
        return pd.read_csv(BytesIO(contents))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as error:
        raise RuntimeError(f"{label} is not a readable CSV") from error


def build_gsc_manifest(
    start_date: str,
    end_date: str,
    row_limit: int,
    stream_paths: dict[str, Path],
    stream_rows: dict[str, list[dict]],
) -> dict:
    streams = {}
    for stream_name in STREAM_SPECS:
        path = stream_paths[stream_name]
        streams[stream_name] = {
            "file": path.name,
            "request": stream_request(stream_name, start_date, end_date, row_limit),
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


def write_gsc_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_and_validate_gsc_artifacts(
    manifest_path: Path,
    expected_start: str,
    expected_end: str,
    stream_paths: dict[str, Path],
    expected_manifest_sha256: str | None = None,
) -> tuple[dict, dict[str, pd.DataFrame], str]:
    manifest_bytes = read_file_bytes(manifest_path, "GSC fetch manifest")
    manifest_sha256 = bytes_sha256(manifest_bytes)
    if expected_manifest_sha256 and manifest_sha256 != expected_manifest_sha256:
        raise RuntimeError("GSC fetch manifest changed after SEO analysis")
    manifest = parse_json_bytes(manifest_bytes, "GSC fetch manifest")

    if manifest.get("version") != MANIFEST_VERSION or manifest.get("status") != "complete":
        raise RuntimeError("GSC fetch manifest is not a completed supported manifest")
    expected_window = {"startDate": expected_start, "endDate": expected_end}
    if manifest.get("expected_window") != expected_window:
        raise RuntimeError(
            f"GSC fetch manifest window mismatch: expected {expected_start}..{expected_end}"
        )

    manifest_streams = manifest.get("streams") or {}
    prepared: dict[str, pd.DataFrame] = {}
    for stream_name, spec in STREAM_SPECS.items():
        path = stream_paths[stream_name]
        stream = manifest_streams.get(stream_name) or {}
        request = stream.get("request") or {}
        row_limit = request.get("rowLimit")
        if not isinstance(row_limit, int) or row_limit < 1:
            raise RuntimeError(f"GSC {stream_name} manifest rowLimit is invalid")
        if request != stream_request(stream_name, expected_start, expected_end, row_limit):
            raise RuntimeError(f"GSC {stream_name} manifest request contract mismatch")
        if stream.get("file") != path.name:
            raise RuntimeError(f"GSC {stream_name} manifest file mismatch")
        contents = read_file_bytes(path, f"GSC {stream_name} CSV")
        if stream.get("sha256") != bytes_sha256(contents):
            raise RuntimeError(f"GSC {stream_name} file does not match its manifest")
        frame = parse_csv_bytes(contents, f"GSC {stream_name} CSV")
        if stream.get("row_count") != len(frame):
            raise RuntimeError(f"GSC {stream_name} row count does not match its manifest")
        required_columns = set(spec["dimensions"] + METRIC_COLUMNS)
        missing_columns = required_columns - set(frame.columns)
        if missing_columns:
            raise RuntimeError(
                f"GSC {stream_name} CSV is missing columns: {sorted(missing_columns)}"
            )

        current = frame.copy()
        current["date"] = pd.to_datetime(current["date"], errors="coerce").dt.normalize()
        if current["date"].isna().any():
            raise RuntimeError(f"GSC {stream_name} CSV contains invalid dates")
        outside = ~current["date"].between(
            pd.Timestamp(expected_start), pd.Timestamp(expected_end)
        )
        if outside.any():
            raise RuntimeError(
                f"GSC {stream_name} CSV contains dates outside {expected_start}..{expected_end}"
            )
        prepared[stream_name] = current

    return manifest, prepared, manifest_sha256


def validate_comparison_window(
    expected_start: str, expected_end: str, required_days: int = 56
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(expected_start)
    end = pd.Timestamp(expected_end)
    required_start = end - pd.Timedelta(days=required_days - 1)
    if start > required_start:
        raise RuntimeError(
            f"GSC request window does not cover the required {required_days}-day comparison"
        )
    return required_start, end
