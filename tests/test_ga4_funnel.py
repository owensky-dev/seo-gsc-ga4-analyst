from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "assets" / "project-template" / "scripts"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

from analyze_seo import build_aggregates
from config import default_gsc_date_range
from fetch_ga4 import build_organic_funnel_request, build_organic_landing_request
from ga4_contract import (
    build_ga4_manifest,
    load_and_validate_ga4_artifacts,
    write_ga4_manifest,
)
from weekly_report import organic_funnel_comparison


class OrganicFunnelTests(unittest.TestCase):
    def test_default_workflow_window_ends_three_days_ago(self) -> None:
        start_date, end_date = default_gsc_date_range()
        expected_end = date.today() - timedelta(days=3)

        self.assertEqual(end_date, expected_end.isoformat())
        self.assertEqual(
            (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days,
            89,
        )

    def test_ga4_requests_keep_sessions_and_dated_events_separate(self) -> None:
        landing = build_organic_landing_request("properties/1", "2026-07-01", "2026-07-07", 100, 0)
        funnel = build_organic_funnel_request("properties/1", "2026-07-01", "2026-07-07", 100, 0)
        self.assertEqual([item.name for item in landing.dimensions], ["date", "landingPagePlusQueryString", "sessionDefaultChannelGroup"])
        self.assertEqual([item.name for item in funnel.dimensions], ["date", "landingPagePlusQueryString", "eventName"])
        self.assertEqual([item.name for item in funnel.metrics], ["eventCount"])
        self.assertEqual(
            list(funnel.dimension_filter.and_group.expressions[1].filter.in_list_filter.values),
            ["add_to_cart", "begin_checkout"],
        )

    def test_weekly_funnel_uses_dated_rows(self) -> None:
        dates = pd.date_range("2026-06-24", periods=14, freq="D")
        landing = pd.DataFrame({"date": dates, "sessions": [10] * 14})
        funnel = pd.DataFrame(
            [
                {"date": "2026-06-25", "eventName": "add_to_cart", "eventCount": 2},
                {"date": "2026-06-26", "eventName": "begin_checkout", "eventCount": 1},
                {"date": "2026-07-05", "eventName": "add_to_cart", "eventCount": 4},
                {"date": "2026-07-06", "eventName": "begin_checkout", "eventCount": 3},
            ]
        )
        result = organic_funnel_comparison(landing, funnel, "2026-07-07")
        self.assertIsNotNone(result)
        self.assertEqual(result["current"]["add_to_cart"], 4)
        self.assertEqual(result["current"]["begin_checkout"], 3)
        self.assertEqual(result["previous"]["add_to_cart"], 2)

    def test_ga4_manifest_must_match_the_shared_gsc_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "landing": root / "ga4_organic_landing_pages_90d.csv",
                "funnel": root / "ga4_organic_funnel_90d.csv",
            }
            frames = {
                "landing": pd.DataFrame(
                    [{"date": "2026-08-15", "sessions": 10}]
                ),
                "funnel": pd.DataFrame(
                    [{"date": "2026-08-15", "eventName": "add_to_cart"}]
                ),
            }
            for stream_name, frame in frames.items():
                frame.to_csv(paths[stream_name], index=False)
            manifest_path = root / "ga4_fetch_manifest.json"
            manifest = build_ga4_manifest(
                "2026-05-18",
                "2026-08-15",
                paths,
                {name: frame.to_dict("records") for name, frame in frames.items()},
            )
            write_ga4_manifest(manifest_path, manifest)

            with self.assertRaisesRegex(RuntimeError, "window mismatch"):
                load_and_validate_ga4_artifacts(
                    manifest_path,
                    "2026-05-19",
                    "2026-08-16",
                    paths,
                )

    def test_page_aggregates_include_funnel_events(self) -> None:
        gsc = pd.DataFrame(
            [{"page_url": "https://example.com/p", "query": "sink", "clicks": 2, "impressions": 20, "ctr": 0.1, "position": 4}]
        )
        gsc_page_daily = pd.DataFrame(
            [{"page_url": "https://example.com/p", "date": "2026-07-01", "clicks": 2, "impressions": 20, "ctr": 0.1, "position": 4}]
        )
        ga4 = pd.DataFrame(
            [{"landing_page_url": "https://example.com/p", "sessions": 10, "engagedSessions": 8, "conversions": 1, "totalRevenue": 100}]
        )
        funnel = pd.DataFrame(
            [
                {"landing_page_url": "https://example.com/p", "eventName": "add_to_cart", "eventCount": 4},
                {"landing_page_url": "https://example.com/p", "eventName": "begin_checkout", "eventCount": 2},
            ]
        )
        _, _, merged = build_aggregates(gsc, gsc_page_daily, ga4, funnel)
        self.assertEqual(merged.iloc[0]["add_to_cart"], 4)
        self.assertEqual(merged.iloc[0]["begin_checkout"], 2)
        self.assertEqual(merged.iloc[0]["cart_to_checkout_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
