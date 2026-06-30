from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
DATA_PROCESSED_DIR = ROOT_DIR / "data" / "processed"
REPORTS_DIR = ROOT_DIR / "reports"


def load_settings() -> dict[str, str]:
    load_dotenv(ROOT_DIR / ".env", override=True)
    required = [
        "SITE_NAME",
        "GSC_SITE_URL",
        "GA4_PROPERTY_ID",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ]
    settings = {key: os.getenv(key, "").strip() for key in required}
    missing = [key for key, value in settings.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required .env values: {', '.join(missing)}")
    settings["SITE_BASE_URL"] = os.getenv("SITE_BASE_URL", "").strip() or infer_site_base_url(settings["GSC_SITE_URL"])
    return settings


def infer_site_base_url(gsc_site_url: str) -> str:
    if gsc_site_url.startswith("sc-domain:"):
        return f"https://{gsc_site_url.removeprefix('sc-domain:')}/"
    return gsc_site_url


def ensure_dirs() -> None:
    for path in [DATA_RAW_DIR, DATA_PROCESSED_DIR, REPORTS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def default_date_range(days: int = 90) -> tuple[str, str]:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def normalize_url(value: str, site_url: str) -> str:
    if not isinstance(value, str):
        return ""

    raw_value = value.strip()
    if not raw_value or raw_value in {"(not set)", "(other)"}:
        return ""

    if raw_value.startswith("/"):
        raw_value = urljoin(site_url, raw_value)

    parsed = urlparse(raw_value)
    if not parsed.scheme or not parsed.netloc:
        parsed = urlparse(urljoin(site_url, raw_value))

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")

    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=path,
        params="",
        query="",
        fragment="",
    )
    return urlunparse(normalized)
