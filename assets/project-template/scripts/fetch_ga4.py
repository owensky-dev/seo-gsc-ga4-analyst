from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange,
    Dimension,
    Filter,
    FilterExpression,
    Metric,
    RunReportRequest,
)
from google.oauth2 import service_account

from config import DATA_RAW_DIR, default_date_range, ensure_dirs, load_settings, normalize_url


COLUMNS = [
    "landingPagePlusQueryString",
    "landing_page_url",
    "sessionDefaultChannelGroup",
    "sessions",
    "engagedSessions",
    "conversions",
    "totalRevenue",
]


def fetch_ga4_rows(
    key_file: str,
    property_id: str,
    site_url: str,
    start_date: str,
    end_date: str,
    limit: int = 100000,
) -> list[dict]:
    credentials = service_account.Credentials.from_service_account_file(key_file)
    client = BetaAnalyticsDataClient(credentials=credentials)
    property_name = f"properties/{property_id}"
    rows: list[dict] = []
    offset = 0

    while True:
        request = RunReportRequest(
            property=property_name,
            dimensions=[
                Dimension(name="landingPagePlusQueryString"),
                Dimension(name="sessionDefaultChannelGroup"),
            ],
            metrics=[
                Metric(name="sessions"),
                Metric(name="engagedSessions"),
                Metric(name="conversions"),
                Metric(name="totalRevenue"),
            ],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            dimension_filter=FilterExpression(
                filter=Filter(
                    field_name="sessionDefaultChannelGroup",
                    string_filter=Filter.StringFilter(
                        match_type=Filter.StringFilter.MatchType.EXACT,
                        value="Organic Search",
                    ),
                )
            ),
            limit=limit,
            offset=offset,
        )
        response = client.run_report(request)
        if not response.rows:
            break

        for row in response.rows:
            landing_page = row.dimension_values[0].value
            rows.append(
                {
                    "landingPagePlusQueryString": landing_page,
                    "landing_page_url": normalize_url(landing_page, site_url),
                    "sessionDefaultChannelGroup": row.dimension_values[1].value,
                    "sessions": float(row.metric_values[0].value or 0),
                    "engagedSessions": float(row.metric_values[1].value or 0),
                    "conversions": float(row.metric_values[2].value or 0),
                    "totalRevenue": float(row.metric_values[3].value or 0),
                }
            )

        if len(response.rows) < limit:
            break
        offset += limit

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch GA4 Organic Search landing page data.")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--out", default=str(DATA_RAW_DIR / "ga4_organic_landing_pages_90d.csv"))
    args = parser.parse_args()

    settings = load_settings()
    ensure_dirs()
    start_date, end_date = (
        (args.start_date, args.end_date)
        if args.start_date and args.end_date
        else default_date_range(args.days)
    )

    rows = fetch_ga4_rows(
        key_file=settings["GOOGLE_APPLICATION_CREDENTIALS"],
        property_id=settings["GA4_PROPERTY_ID"],
        site_url=settings["SITE_BASE_URL"],
        start_date=start_date,
        end_date=end_date,
    )
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=COLUMNS).to_csv(output_path, index=False)
    print(f"GA4 rows={len(rows)} date_range={start_date}..{end_date} out={output_path}")


if __name__ == "__main__":
    main()
