from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "assets" / "project-template" / "scripts"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

from analysis_contract import (
    build_analysis_manifest,
    load_and_validate_analysis_artifacts,
    write_analysis_manifest,
)


class AnalysisContractTests(unittest.TestCase):
    def test_weekly_contract_rejects_refreshed_raw_before_reanalysis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_paths = {
                "gsc": root / "gsc_fetch_manifest.json",
                "ga4": root / "ga4_fetch_manifest.json",
            }
            artifact_paths = {
                "gsc_pages": root / "gsc_pages_90d.csv",
                "gsc_keywords": root / "gsc_keywords_90d.csv",
                "seo_merged_pages": root / "seo_merged_pages_90d.csv",
                "seo_opportunities_csv": root / "seo_opportunities.csv",
                "seo_opportunities_md": root / "seo_opportunities.md",
            }
            for name, path in source_paths.items():
                path.write_text(f'{{"source": "{name}", "run": 1}}\n', encoding="utf-8")
            for name, path in artifact_paths.items():
                path.write_text(f"artifact={name}\n", encoding="utf-8")

            manifest_path = root / "seo_analysis_manifest.json"
            manifest = build_analysis_manifest(
                "2026-05-18",
                "2026-08-15",
                source_paths,
                artifact_paths,
            )
            write_analysis_manifest(manifest_path, manifest)
            load_and_validate_analysis_artifacts(
                manifest_path,
                "2026-05-18",
                "2026-08-15",
                source_paths,
                artifact_paths,
            )

            source_paths["gsc"].write_text(
                '{"source": "gsc", "run": 2}\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "source manifest changed"):
                load_and_validate_analysis_artifacts(
                    manifest_path,
                    "2026-05-18",
                    "2026-08-15",
                    source_paths,
                    artifact_paths,
                )

    def test_weekly_contract_rejects_changed_processed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_paths = {
                "gsc": root / "gsc_fetch_manifest.json",
                "ga4": root / "ga4_fetch_manifest.json",
            }
            artifact_paths = {"seo_merged_pages": root / "seo_merged_pages_90d.csv"}
            for path in source_paths.values():
                path.write_text("{}\n", encoding="utf-8")
            artifact_paths["seo_merged_pages"].write_text(
                "page_url,clicks\nhttps://example.com,1\n", encoding="utf-8"
            )
            manifest_path = root / "seo_analysis_manifest.json"
            write_analysis_manifest(
                manifest_path,
                build_analysis_manifest(
                    "2026-05-18",
                    "2026-08-15",
                    source_paths,
                    artifact_paths,
                ),
            )

            artifact_paths["seo_merged_pages"].write_text(
                "page_url,clicks\nhttps://example.com,2\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "artifact does not match"):
                load_and_validate_analysis_artifacts(
                    manifest_path,
                    "2026-05-18",
                    "2026-08-15",
                    source_paths,
                    artifact_paths,
                )


if __name__ == "__main__":
    unittest.main()
