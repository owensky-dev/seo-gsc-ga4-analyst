from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "assets" / "project-template" / "scripts"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

from analyze_seo import build_aggregates, summarize_gsc_site, validate_gsc_daily_alignment
from fetch_gsc import (
    DETAIL_DIMENSIONS,
    PAGE_DAILY_DIMENSIONS,
    SITE_DAILY_DIMENSIONS,
    build_search_analytics_body,
)


class GscGrainTests(unittest.TestCase):
    def test_search_analytics_requests_keep_three_grains_separate(self) -> None:
        detail = build_search_analytics_body(
            "2026-08-01", "2026-08-14", DETAIL_DIMENSIONS, 25000, 0
        )
        site_daily = build_search_analytics_body(
            "2026-08-01",
            "2026-08-14",
            SITE_DAILY_DIMENSIONS,
            25000,
            0,
            "byProperty",
        )
        page_daily = build_search_analytics_body(
            "2026-08-01",
            "2026-08-14",
            PAGE_DAILY_DIMENSIONS,
            25000,
            0,
            "byPage",
        )

        self.assertEqual(detail["dimensions"], ["date", "page", "query", "country", "device"])
        self.assertEqual(detail["type"], "web")
        self.assertNotIn("aggregationType", detail)
        self.assertEqual(site_daily["dimensions"], ["date"])
        self.assertEqual(site_daily["aggregationType"], "byProperty")
        self.assertEqual(page_daily["dimensions"], ["date", "page"])
        self.assertEqual(page_daily["aggregationType"], "byPage")

    def test_site_totals_route_to_property_daily_instead_of_query_detail(self) -> None:
        dates = pd.date_range("2026-08-01", periods=14, freq="D")
        site_daily = pd.DataFrame(
            {
                "date": dates,
                "clicks": [0] * 13 + [44],
                "impressions": [0] * 13 + [4854],
                "ctr": [0] * 13 + [44 / 4854],
                "position": [0] * 13 + [38.7],
            }
        )
        query_detail = pd.DataFrame([{"clicks": 6, "impressions": 4002}])

        summary = summarize_gsc_site(site_daily)

        self.assertEqual(query_detail["clicks"].sum(), 6)
        self.assertEqual(summary["clicks"], 44)
        self.assertEqual(summary["impressions"], 4854)
        self.assertAlmostEqual(summary["ctr"], 44 / 4854)

    def test_site_daily_missing_or_incomplete_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "empty or missing"):
            summarize_gsc_site(pd.DataFrame())

        incomplete = pd.DataFrame(
            {
                "date": pd.date_range("2026-08-01", periods=13, freq="D"),
                "clicks": [1] * 13,
                "impressions": [10] * 13,
                "ctr": [0.1] * 13,
                "position": [5] * 13,
            }
        )
        with self.assertRaisesRegex(RuntimeError, "coverage is incomplete"):
            summarize_gsc_site(incomplete)

    def test_page_daily_missing_site_date_fails_closed(self) -> None:
        site_daily = pd.DataFrame(
            {"date": pd.date_range("2026-08-01", periods=14, freq="D")}
        )
        page_daily = pd.DataFrame(
            {"date": pd.date_range("2026-08-01", periods=13, freq="D")}
        )

        with self.assertRaisesRegex(RuntimeError, "missing site dates"):
            validate_gsc_daily_alignment(site_daily, page_daily)

    def test_page_totals_use_page_daily_and_keywords_use_query_detail(self) -> None:
        query_detail = pd.DataFrame(
            [
                {
                    "page_url": "https://example.com/p",
                    "query": "sink",
                    "clicks": 6,
                    "impressions": 4002,
                    "ctr": 6 / 4002,
                    "position": 40,
                }
            ]
        )
        page_daily = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-08-14"),
                    "page_url": "https://example.com/p",
                    "clicks": 44,
                    "impressions": 4854,
                    "ctr": 44 / 4854,
                    "position": 38.7,
                }
            ]
        )
        ga4 = pd.DataFrame(
            [
                {
                    "landing_page_url": "https://example.com/p",
                    "sessions": 10,
                    "engagedSessions": 8,
                    "conversions": 1,
                    "totalRevenue": 100,
                }
            ]
        )

        pages, keywords, merged = build_aggregates(
            query_detail, page_daily, ga4, pd.DataFrame()
        )

        self.assertEqual(pages.iloc[0]["clicks"], 44)
        self.assertEqual(keywords.iloc[0]["clicks"], 6)
        self.assertEqual(merged.iloc[0]["clicks"], 44)


if __name__ == "__main__":
    unittest.main()
