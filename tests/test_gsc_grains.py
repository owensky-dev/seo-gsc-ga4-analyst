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

from analyze_seo import (
    build_aggregates,
    build_opportunities,
    click_drop_opportunities,
    prepare_gsc_page_daily,
    summarize_gsc_site,
)
from fetch_gsc import (
    DETAIL_DIMENSIONS,
    PAGE_DAILY_DIMENSIONS,
    SITE_DAILY_DIMENSIONS,
    build_search_analytics_body,
    fetch_gsc_rows,
    main as fetch_gsc_main,
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
    if site_dates is None:
        site_dates = [start_date, end_date]
    if page_dates is None:
        page_dates = [start_date, end_date]
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
            ],
            columns=[
                "date",
                "page",
                "query",
                "country",
                "device",
                "clicks",
                "impressions",
                "ctr",
                "position",
            ],
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
            ],
            columns=["date", "clicks", "impressions", "ctr", "position"],
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
            ],
            columns=["date", "page", "clicks", "impressions", "ctr", "position"],
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

    def test_site_daily_without_contract_headers_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "missing columns"):
            summarize_gsc_site(pd.DataFrame())

    def test_old_fourteen_day_manifest_cannot_satisfy_ninety_day_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, paths, _ = write_gsc_artifacts(
                Path(directory), "2026-08-02", "2026-08-15"
            )
            with self.assertRaisesRegex(RuntimeError, "window mismatch"):
                load_and_validate_gsc_artifacts(
                    manifest_path,
                    "2026-05-18",
                    "2026-08-15",
                    paths,
                )

    def test_stale_ninety_day_manifest_cannot_satisfy_current_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, paths, _ = write_gsc_artifacts(
                Path(directory), "2026-05-17", "2026-08-14"
            )
            with self.assertRaisesRegex(RuntimeError, "window mismatch"):
                load_and_validate_gsc_artifacts(
                    manifest_path,
                    "2026-05-18",
                    "2026-08-15",
                    paths,
                )

    def test_complete_manifest_allows_legitimate_no_data_days(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, paths, _ = write_gsc_artifacts(
                Path(directory),
                "2026-05-18",
                "2026-08-15",
                site_dates=["2026-05-18", "2026-06-20", "2026-08-15"],
                page_dates=["2026-05-18", "2026-07-20", "2026-08-15"],
            )
            _, prepared, _ = load_and_validate_gsc_artifacts(
                manifest_path,
                "2026-05-18",
                "2026-08-15",
                paths,
            )

        self.assertEqual(len(prepared["site_daily"]), 3)
        self.assertEqual(len(prepared["page_daily"]), 3)

    def test_complete_manifest_allows_an_entirely_empty_gsc_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "detail": root / "gsc_90d.csv",
                "site_daily": root / "gsc_daily_90d.csv",
                "page_daily": root / "gsc_page_daily_90d.csv",
            }
            manifest_path = root / "gsc_fetch_manifest.json"
            argv = [
                "fetch_gsc.py",
                "--start-date",
                "2026-05-18",
                "--end-date",
                "2026-08-15",
                "--out",
                str(paths["detail"]),
                "--daily-out",
                str(paths["site_daily"]),
                "--page-daily-out",
                str(paths["page_daily"]),
                "--manifest-out",
                str(manifest_path),
            ]
            with patch(
                "fetch_gsc.load_settings",
                return_value={
                    "GOOGLE_APPLICATION_CREDENTIALS": "unused.json",
                    "GSC_SITE_URL": "sc-domain:example.com",
                },
            ), patch("fetch_gsc.ensure_dirs"), patch(
                "fetch_gsc.fetch_gsc_rows", return_value=[]
            ) as fetch_mock, patch("builtins.print"), patch.object(sys, "argv", argv):
                fetch_gsc_main()
            _, prepared, _ = load_and_validate_gsc_artifacts(
                manifest_path,
                "2026-05-18",
                "2026-08-15",
                paths,
            )

        self.assertEqual(fetch_mock.call_count, 3)
        summary = summarize_gsc_site(prepared["site_daily"])
        self.assertEqual(
            summary,
            {"clicks": 0.0, "impressions": 0.0, "ctr": 0.0, "position": 0.0},
        )
        detail = prepared["detail"].copy()
        detail["page_url"] = pd.Series(dtype="object")
        page_daily = prepare_gsc_page_daily(
            prepared["page_daily"], "https://example.com/"
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
            detail, page_daily, ga4, pd.DataFrame()
        )
        self.assertTrue(pages.empty)
        self.assertTrue(keywords.empty)
        self.assertEqual(len(merged), 1)
        self.assertEqual(
            click_drop_opportunities(
                page_daily, merged, "2026-05-18", "2026-08-15"
            ),
            [],
        )
        self.assertEqual(
            build_opportunities(
                page_daily,
                keywords,
                merged,
                0.0,
                "2026-05-18",
                "2026-08-15",
            ),
            [],
        )

    def test_gsc_validator_hashes_and_parses_the_same_file_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, paths, _ = write_gsc_artifacts(
                Path(directory), "2026-05-18", "2026-08-15"
            )
            original_read_bytes = Path.read_bytes
            replaced = False

            def racing_read_bytes(path: Path) -> bytes:
                nonlocal replaced
                contents = original_read_bytes(path)
                if path == paths["site_daily"] and not replaced:
                    replaced = True
                    pd.DataFrame(
                        [
                            {
                                "date": "2026-08-15",
                                "clicks": 999,
                                "impressions": 1000,
                                "ctr": 0.999,
                                "position": 1,
                            }
                        ]
                    ).to_csv(path, index=False)
                return contents

            with patch.object(Path, "read_bytes", racing_read_bytes):
                _, prepared, _ = load_and_validate_gsc_artifacts(
                    manifest_path,
                    "2026-05-18",
                    "2026-08-15",
                    paths,
                )

            self.assertTrue(replaced)
            self.assertEqual(prepared["site_daily"]["clicks"].sum(), 44)
            self.assertEqual(pd.read_csv(paths["site_daily"])["clicks"].sum(), 999)

    def test_page_date_outside_shared_window_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path, paths, _ = write_gsc_artifacts(
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
                )

    def test_page_manifest_request_must_match_site_window_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path, paths, _ = write_gsc_artifacts(
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
