from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "assets" / "project-template" / "scripts"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

from analyze_seo import build_aggregates, click_drop_opportunities, summarize_gsc_site
from fetch_gsc import (
    DETAIL_DIMENSIONS,
    PAGE_DAILY_DIMENSIONS,
    SITE_DAILY_DIMENSIONS,
    build_search_analytics_body,
    fetch_gsc_rows,
)
from gsc_contract import (
    build_gsc_manifest,
    load_and_validate_gsc_artifacts,
    validate_comparison_window,
    write_gsc_manifest,
)


def write_gsc_artifacts(
    root: Path,
    start_date: str,
    end_date: str,
    *,
    site_dates: list[str] | None = None,
    page_dates: list[str] | None = None,
) -> tuple[Path, dict[str, Path], dict[str, pd.DataFrame]]:
    site_dates = site_dates or [start_date, end_date]
    page_dates = page_dates or [start_date, end_date]
    frames = {
        "detail": pd.DataFrame(
            [
                {
                    "date": end_date,
                    "page": "https://example.com/p",
                    "query": "sink",
                    "country": "usa",
                    "device": "desktop",
                    "clicks": 6,
                    "impressions": 100,
                    "ctr": 0.06,
                    "position": 8,
                }
            ]
        ),
        "site_daily": pd.DataFrame(
            [
                {
                    "date": value,
                    "clicks": 22,
                    "impressions": 1000,
                    "ctr": 0.022,
                    "position": 10,
                }
                for value in site_dates
            ]
        ),
        "page_daily": pd.DataFrame(
            [
                {
                    "date": value,
                    "page": "https://example.com/p",
                    "clicks": 22,
                    "impressions": 1000,
                    "ctr": 0.022,
                    "position": 10,
                }
                for value in page_dates
            ]
        ),
    }
    paths = {
        "detail": root / "gsc_90d.csv",
        "site_daily": root / "gsc_daily_90d.csv",
        "page_daily": root / "gsc_page_daily_90d.csv",
    }
    for stream_name, frame in frames.items():
        frame.to_csv(paths[stream_name], index=False)
    manifest_path = root / "gsc_fetch_manifest.json"
    manifest = build_gsc_manifest(
        start_date,
        end_date,
        25000,
        paths,
        {name: frame.to_dict("records") for name, frame in frames.items()},
    )
    write_gsc_manifest(manifest_path, manifest)
    return manifest_path, paths, frames


class GscGrainTests(unittest.TestCase):
    def test_search_analytics_requests_keep_three_grains_separate(self) -> None:
        detail = build_search_analytics_body(
            "2026-05-18", "2026-08-15", DETAIL_DIMENSIONS, 25000, 0
        )
        site_daily = build_search_analytics_body(
            "2026-05-18",
            "2026-08-15",
            SITE_DAILY_DIMENSIONS,
            25000,
            0,
            "byProperty",
        )
        page_daily = build_search_analytics_body(
            "2026-05-18",
            "2026-08-15",
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

    def test_fetch_gsc_rows_sends_body_and_paginates(self) -> None:
        with patch(
            "fetch_gsc.service_account.Credentials.from_service_account_file"
        ), patch("fetch_gsc.build") as build_mock:
            query = build_mock.return_value.searchanalytics.return_value.query
            query.return_value.execute.side_effect = [
                {
                    "rows": [
                        {"keys": ["2026-08-01"], "clicks": 1},
                        {"keys": ["2026-08-02"], "clicks": 2},
                    ]
                },
                {"rows": [{"keys": ["2026-08-03"], "clicks": 3}]},
            ]

            rows = fetch_gsc_rows(
                "unused.json",
                "sc-domain:example.com",
                "2026-05-18",
                "2026-08-15",
                row_limit=2,
                dimensions=SITE_DAILY_DIMENSIONS,
                aggregation_type="byProperty",
            )

        self.assertEqual([row["clicks"] for row in rows], [1, 2, 3])
        self.assertEqual(query.call_count, 2)
        first = query.call_args_list[0].kwargs
        second = query.call_args_list[1].kwargs
        self.assertEqual(first["siteUrl"], "sc-domain:example.com")
        self.assertEqual(first["body"]["startRow"], 0)
        self.assertEqual(first["body"]["aggregationType"], "byProperty")
        self.assertEqual(first["body"]["type"], "web")
        self.assertEqual(second["body"]["startRow"], 2)

    def test_site_totals_route_to_property_daily_instead_of_query_detail(self) -> None:
        site_daily = pd.DataFrame(
            [
                {
                    "date": "2026-08-15",
                    "clicks": 44,
                    "impressions": 4854,
                    "ctr": 44 / 4854,
                    "position": 38.7,
                }
            ]
        )
        query_detail = pd.DataFrame([{"clicks": 6, "impressions": 4002}])

        summary = summarize_gsc_site(site_daily)

        self.assertEqual(query_detail["clicks"].sum(), 6)
        self.assertEqual(summary["clicks"], 44)
        self.assertEqual(summary["impressions"], 4854)
        self.assertAlmostEqual(summary["ctr"], 44 / 4854)

    def test_site_daily_empty_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "empty or missing"):
            summarize_gsc_site(pd.DataFrame())

    def test_old_fourteen_day_manifest_cannot_satisfy_ninety_day_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, paths, frames = write_gsc_artifacts(
                Path(directory), "2026-08-02", "2026-08-15"
            )
            with self.assertRaisesRegex(RuntimeError, "window mismatch"):
                load_and_validate_gsc_artifacts(
                    manifest_path,
                    "2026-05-18",
                    "2026-08-15",
                    paths,
                    frames,
                )

    def test_stale_ninety_day_manifest_cannot_satisfy_current_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, paths, frames = write_gsc_artifacts(
                Path(directory), "2026-05-17", "2026-08-14"
            )
            with self.assertRaisesRegex(RuntimeError, "window mismatch"):
                load_and_validate_gsc_artifacts(
                    manifest_path,
                    "2026-05-18",
                    "2026-08-15",
                    paths,
                    frames,
                )

    def test_complete_manifest_allows_legitimate_no_data_days(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, paths, frames = write_gsc_artifacts(
                Path(directory),
                "2026-05-18",
                "2026-08-15",
                site_dates=["2026-05-18", "2026-06-20", "2026-08-15"],
                page_dates=["2026-05-18", "2026-07-20", "2026-08-15"],
            )
            _, prepared = load_and_validate_gsc_artifacts(
                manifest_path,
                "2026-05-18",
                "2026-08-15",
                paths,
                frames,
            )

        self.assertEqual(len(prepared["site_daily"]), 3)
        self.assertEqual(len(prepared["page_daily"]), 3)

    def test_page_date_outside_shared_window_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, paths, frames = write_gsc_artifacts(
                Path(directory),
                "2026-05-18",
                "2026-08-15",
                page_dates=["2026-05-18", "2026-08-16"],
            )
            with self.assertRaisesRegex(RuntimeError, "dates outside"):
                load_and_validate_gsc_artifacts(
                    manifest_path,
                    "2026-05-18",
                    "2026-08-15",
                    paths,
                    frames,
                )

    def test_page_manifest_request_must_match_site_window_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, paths, frames = write_gsc_artifacts(
                root, "2026-05-18", "2026-08-15"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["streams"]["page_daily"]["request"]["startDate"] = "2026-05-19"
            write_gsc_manifest(manifest_path, manifest)

            with self.assertRaisesRegex(RuntimeError, "request contract mismatch"):
                load_and_validate_gsc_artifacts(
                    manifest_path,
                    "2026-05-18",
                    "2026-08-15",
                    paths,
                    frames,
                )

    def test_click_drop_uses_full_fifty_six_days_and_zero_fills_no_data_days(self) -> None:
        page_url = "https://example.com/p"
        page_daily = pd.DataFrame(
            [
                {
                    "date": pd.Timestamp("2026-06-21"),
                    "page_url": page_url,
                    "clicks": 20,
                }
            ]
        )
        merged = pd.DataFrame(
            [
                {
                    "page_url": page_url,
                    "clicks": 20,
                    "impressions": 500,
                    "ctr": 0.04,
                    "position": 10,
                    "sessions": 30,
                    "conversions": 1,
                    "totalRevenue": 100,
                }
            ]
        )

        opportunities = click_drop_opportunities(
            page_daily, merged, "2026-05-18", "2026-08-15"
        )

        self.assertEqual(len(opportunities), 1)
        self.assertIn("最近28天点击 0，前28天 20", opportunities[0].recommendation)
        with self.assertRaisesRegex(RuntimeError, "required 56-day comparison"):
            validate_comparison_window("2026-06-22", "2026-08-15")

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
                    "date": pd.Timestamp("2026-08-15"),
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
