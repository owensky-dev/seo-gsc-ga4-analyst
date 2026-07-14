from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "assets" / "project-template" / "scripts"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

from fetch_ga4 import build_organic_funnel_request, build_organic_landing_request
from analyze_seo import build_aggregates
from weekly_report import organic_funnel_comparison


class OrganicFunnelTests(unittest.TestCase):
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
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dates = pd.date_range("2026-06-24", periods=14, freq="D")
            pd.DataFrame({"date": dates, "sessions": [10] * 14}).to_csv(root / "landing.csv", index=False)
            pd.DataFrame(
                [
                    {"date": "2026-06-25", "eventName": "add_to_cart", "eventCount": 2},
                    {"date": "2026-06-26", "eventName": "begin_checkout", "eventCount": 1},
                    {"date": "2026-07-05", "eventName": "add_to_cart", "eventCount": 4},
                    {"date": "2026-07-06", "eventName": "begin_checkout", "eventCount": 3},
                ]
            ).to_csv(root / "funnel.csv", index=False)
            result = organic_funnel_comparison(root / "landing.csv", root / "funnel.csv")
        self.assertIsNotNone(result)
        self.assertEqual(result["current"]["add_to_cart"], 4)
        self.assertEqual(result["current"]["begin_checkout"], 3)
        self.assertEqual(result["previous"]["add_to_cart"], 2)

    def test_page_aggregates_include_funnel_events(self) -> None:
        gsc = pd.DataFrame(
            [{"page_url": "https://example.com/p", "query": "sink", "clicks": 2, "impressions": 20, "ctr": 0.1, "position": 4}]
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
        _, _, merged = build_aggregates(gsc, ga4, funnel)
        self.assertEqual(merged.iloc[0]["add_to_cart"], 4)
        self.assertEqual(merged.iloc[0]["begin_checkout"], 2)
        self.assertEqual(merged.iloc[0]["cart_to_checkout_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
