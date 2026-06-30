from __future__ import annotations

import argparse
import shutil
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = SKILL_DIR / "assets" / "project-template"


def copy_tree(source: Path, target: Path, force: bool = False) -> None:
    for source_path in source.rglob("*"):
        relative = source_path.relative_to(source)
        if "__pycache__" in relative.parts or source_path.suffix == ".pyc":
            continue
        target_path = target / relative
        if source_path.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue
        if target_path.exists() and not force:
            print(f"skip existing: {target_path}")
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        print(f"wrote: {target_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a local GSC/GA4 SEO analysis project.")
    parser.add_argument("--target", default=".", help="Project directory to create or update.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing template files.")
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    copy_tree(TEMPLATE_DIR, target, force=args.force)
    for path in [
        target / "data" / "raw",
        target / "data" / "processed",
        target / "reports",
        target / "outputs",
    ]:
        path.mkdir(parents=True, exist_ok=True)
    print(f"SEO analysis project ready: {target}")
    print("Next: copy .env.example to .env and fill local credentials.")


if __name__ == "__main__":
    main()
