"""Bundle a private offline report; the browser verifies data before analysis."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def bundle(viewer: Path, payload: dict | None = None) -> str:
    html = (viewer / "index.html").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="style.css">', '<style>' + (viewer / "style.css").read_text(encoding="utf-8") + '</style>')
    for name in ["engine.js", "app.js"]:
        html = html.replace(f'<script src="{name}"></script>', '<script>' + (viewer / name).read_text(encoding="utf-8") + '</script>')
    if payload is not None:
        encoded = json.dumps(payload, ensure_ascii=True).replace("<", "\\u003c")
        html = html.replace('id="seed">null</script>', f'id="seed">{encoded}</script>')
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.manifest and not args.csv:
        parser.error("--manifest requires --csv")
    payload = None
    if args.csv:
        # Preserve CRLF/BOM: browser hashes exactly the imported UTF-8 bytes.
        text = args.csv.read_bytes().decode("utf-8")
        if len(text.encode("utf-8")) > 20 * 1024 * 1024:
            parser.error("CSV exceeds 20 MB")
        payload = {"text": text, "filename": args.csv.name,
                   "manifest": json.loads(args.manifest.read_bytes()) if args.manifest else None}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(bundle(Path(__file__).resolve().parents[1] / "decay", payload), encoding="utf-8")
    print(f"Packaged: {args.out}. Open and verify the report before treating analysis as complete.")


if __name__ == "__main__":
    main()
