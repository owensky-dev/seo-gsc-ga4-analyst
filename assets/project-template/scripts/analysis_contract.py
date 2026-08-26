from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from gsc_contract import file_sha256


MANIFEST_VERSION = 1


def build_analysis_manifest(
    start_date: str,
    end_date: str,
    source_manifest_paths: dict[str, Path],
    artifact_paths: dict[str, Path],
) -> dict:
    return {
        "version": MANIFEST_VERSION,
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "expected_window": {"startDate": start_date, "endDate": end_date},
        "source_manifests": {
            name: {"file": path.name, "sha256": file_sha256(path)}
            for name, path in source_manifest_paths.items()
        },
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
) -> dict:
    if not manifest_path.exists():
        raise RuntimeError(f"SEO analysis manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise RuntimeError(f"SEO analysis manifest is unreadable: {manifest_path}") from error

    if manifest.get("version") != MANIFEST_VERSION or manifest.get("status") != "complete":
        raise RuntimeError("SEO analysis manifest is not a completed supported manifest")
    expected_window = {"startDate": expected_start, "endDate": expected_end}
    if manifest.get("expected_window") != expected_window:
        raise RuntimeError(
            f"SEO analysis manifest window mismatch: expected {expected_start}..{expected_end}"
        )

    for name, path in source_manifest_paths.items():
        recorded = (manifest.get("source_manifests") or {}).get(name) or {}
        if recorded.get("file") != path.name:
            raise RuntimeError(f"SEO analysis {name} source manifest file mismatch")
        if not path.exists() or recorded.get("sha256") != file_sha256(path):
            raise RuntimeError(
                f"SEO analysis is stale because the {name} source manifest changed"
            )

    for name, path in artifact_paths.items():
        recorded = (manifest.get("artifacts") or {}).get(name) or {}
        if recorded.get("file") != path.name:
            raise RuntimeError(f"SEO analysis {name} artifact file mismatch")
        if not path.exists() or recorded.get("sha256") != file_sha256(path):
            raise RuntimeError(f"SEO analysis {name} artifact does not match its manifest")

    return manifest
