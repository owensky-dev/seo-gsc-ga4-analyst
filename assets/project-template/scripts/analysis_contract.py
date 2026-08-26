from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gsc_contract import (
    bytes_sha256,
    file_sha256,
    parse_csv_bytes,
    parse_json_bytes,
    read_file_bytes,
)


MANIFEST_VERSION = 1


def build_analysis_manifest(
    start_date: str,
    end_date: str,
    source_manifests: dict[str, dict[str, str]],
    artifact_paths: dict[str, Path],
) -> dict:
    return {
        "version": MANIFEST_VERSION,
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "expected_window": {"startDate": start_date, "endDate": end_date},
        "source_manifests": source_manifests,
        "artifacts": {
            name: {"file": path.name, "sha256": file_sha256(path)}
            for name, path in artifact_paths.items()
        },
    }


def write_analysis_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def load_and_validate_analysis_artifacts(
    manifest_path: Path,
    expected_start: str,
    expected_end: str,
    source_manifest_paths: dict[str, Path],
    artifact_paths: dict[str, Path],
) -> tuple[dict, dict[str, pd.DataFrame], dict[str, dict[str, str]]]:
    manifest_bytes = read_file_bytes(manifest_path, "SEO analysis manifest")
    manifest = parse_json_bytes(manifest_bytes, "SEO analysis manifest")

    if manifest.get("version") != MANIFEST_VERSION or manifest.get("status") != "complete":
        raise RuntimeError("SEO analysis manifest is not a completed supported manifest")
    expected_window = {"startDate": expected_start, "endDate": expected_end}
    if manifest.get("expected_window") != expected_window:
        raise RuntimeError(
            f"SEO analysis manifest window mismatch: expected {expected_start}..{expected_end}"
        )

    source_manifests: dict[str, dict[str, str]] = {}
    for name, path in source_manifest_paths.items():
        recorded = (manifest.get("source_manifests") or {}).get(name) or {}
        if recorded.get("file") != path.name:
            raise RuntimeError(f"SEO analysis {name} source manifest file mismatch")
        digest = recorded.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise RuntimeError(f"SEO analysis {name} source manifest hash is invalid")
        source_manifests[name] = {"file": path.name, "sha256": digest}

    frames: dict[str, pd.DataFrame] = {}
    for name, path in artifact_paths.items():
        recorded = (manifest.get("artifacts") or {}).get(name) or {}
        if recorded.get("file") != path.name:
            raise RuntimeError(f"SEO analysis {name} artifact file mismatch")
        contents = read_file_bytes(path, f"SEO analysis {name} artifact")
        if recorded.get("sha256") != bytes_sha256(contents):
            raise RuntimeError(f"SEO analysis {name} artifact does not match its manifest")
        if path.suffix.lower() == ".csv":
            frames[name] = parse_csv_bytes(
                contents, f"SEO analysis {name} artifact"
            )

    return manifest, frames, source_manifests
