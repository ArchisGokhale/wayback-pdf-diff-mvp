from __future__ import annotations

import argparse
import json
from pathlib import Path

from .diff_engine import diff_pdf_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare two PDF files and emit structured diff JSON.")
    parser.add_argument("old_pdf", type=Path, help="Path to old PDF")
    parser.add_argument("new_pdf", type=Path, help="Path to new PDF")
    parser.add_argument("--context", type=int, default=3, help="Unified diff context lines")
    parser.add_argument("--granularity", choices=["line", "block"], default="line")
    parser.add_argument("--enable-ocr", action="store_true", help="Enable optional OCR fallback")
    parser.add_argument("--out", type=Path, help="Output JSON file. Defaults to stdout.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    result = diff_pdf_files(
        args.old_pdf,
        args.new_pdf,
        context=args.context,
        granularity=args.granularity,
        enable_ocr=args.enable_ocr,
    )
    payload = result.as_dict()

    if args.out:
        args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote diff JSON to {args.out}")
    else:
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
