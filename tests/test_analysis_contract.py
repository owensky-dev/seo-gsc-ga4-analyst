from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


TEMPLATE_SCRIPTS = Path(__file__).resolve().parents[1] / "assets" / "project-template" / "scripts"
sys.path.insert(0, str(TEMPLATE_SCRIPTS))

from analysis_contract import (
    build_analysis_manifest,
    load_and_validate_analysis_artifacts,
    write_analysis_manifest,
)
from gsc_contract import file_sha256, load_and_validate_gsc_artifacts


def source_records(paths: dict[str, Path]) -> dict[str, dict[str, str]]:
    return {
        name: {"file": path.name, "sha256": file_sha256(path)}
        for name, path in paths.items()
    }


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
                source_records(source_paths),
                artifact_paths,
            )
            write_analysis_manifest(manifest_path, manifest)
            _, _, bound_sources = load_and_validate_analysis_artifacts(
                manifest_path,
                "2026-05-18",
                "2026-08-15",
                source_paths,
                artifact_paths,
            )

            source_paths["gsc"].write_text(
                '{"source": "gsc", "run": 2}\n', encoding="utf-8"
            )
            with self.assertRaisesRegex(RuntimeError, "changed after SEO analysis"):
                load_and_validate_gsc_artifacts(
                    source_paths["gsc"],
                    "2026-05-18",
                    "2026-08-15",
                    {},
                    bound_sources["gsc"]["sha256"],
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
                    source_records(source_paths),
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

    def test_analysis_validator_hashes_and_parses_the_same_artifact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_paths = {
                "gsc": root / "gsc_fetch_manifest.json",
                "ga4": root / "ga4_fetch_manifest.json",
            }
            for path in source_paths.values():
                path.write_text("{}\n", encoding="utf-8")
            artifact_path = root / "seo_merged_pages_90d.csv"
            artifact_path.write_text(
                "page_url,clicks\nhttps://example.com,1\n", encoding="utf-8"
            )
            artifact_paths = {"seo_merged_pages": artifact_path}
            manifest_path = root / "seo_analysis_manifest.json"
            write_analysis_manifest(
                manifest_path,
                build_analysis_manifest(
                    "2026-05-18",
                    "2026-08-15",
                    source_records(source_paths),
                    artifact_paths,
                ),
            )
            original_read_bytes = Path.read_bytes
            replaced = False

            def racing_read_bytes(path: Path) -> bytes:
                nonlocal replaced
                contents = original_read_bytes(path)
                if path == artifact_path and not replaced:
                    replaced = True
                    path.write_text(
                        "page_url,clicks\nhttps://example.com,2\n", encoding="utf-8"
                    )
                return contents

            with patch.object(Path, "read_bytes", racing_read_bytes):
                _, frames, _ = load_and_validate_analysis_artifacts(
                    manifest_path,
                    "2026-05-18",
                    "2026-08-15",
                    source_paths,
                    artifact_paths,
                )

            self.assertTrue(replaced)
            self.assertEqual(frames["seo_merged_pages"]["clicks"].sum(), 1)
            self.assertEqual(pd.read_csv(artifact_path)["clicks"].sum(), 2)


if __name__ == "__main__":
    unittest.main()
