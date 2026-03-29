from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher, unified_diff
from pathlib import Path
from typing import Any

from .extractor import PdfInput, extract_pdf_text


@dataclass
class DiffSummary:
    lines_added: int
    lines_removed: int
    lines_changed: int


@dataclass
class LineRef:
    global_line: int
    page: int
    line_on_page: int
    text: str


@dataclass
class DiffResult:
    schema_version: str
    changed: bool
    summary: DiffSummary
    documents: dict[str, dict[str, int]]
    unified_diff: str
    hunks: list[dict[str, Any]]
    changes: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _compute_changes(
    old_lines: list[LineRef],
    new_lines: list[LineRef],
) -> tuple[list[dict[str, Any]], DiffSummary]:
    old_text = [line.text for line in old_lines]
    new_text = [line.text for line in new_lines]
    matcher = SequenceMatcher(a=old_text, b=new_text)
    hunks: list[dict[str, Any]] = []

    added = 0
    removed = 0
    changed = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert":
            added += j2 - j1
        elif tag == "delete":
            removed += i2 - i1
        elif tag == "replace":
            removed += i2 - i1
            added += j2 - j1
            changed += max(i2 - i1, j2 - j1)

        hunks.append(
            {
                "op": tag,
                "old": {
                    "start": i1,
                    "end": i2,
                    "lines": [asdict(line) for line in old_lines[i1:i2]],
                },
                "new": {
                    "start": j1,
                    "end": j2,
                    "lines": [asdict(line) for line in new_lines[j1:j2]],
                },
            }
        )

    return hunks, DiffSummary(lines_added=added, lines_removed=removed, lines_changed=changed)


def diff_text(old_text: str, new_text: str, context: int = 3) -> DiffResult:
    old_lines = [
        LineRef(global_line=idx + 1, page=1, line_on_page=idx + 1, text=value)
        for idx, value in enumerate(old_text.splitlines())
    ]
    new_lines = [
        LineRef(global_line=idx + 1, page=1, line_on_page=idx + 1, text=value)
        for idx, value in enumerate(new_text.splitlines())
    ]
    old_text_lines = [line.text for line in old_lines]
    new_text_lines = [line.text for line in new_lines]

    patch = "\n".join(
        unified_diff(
            old_text_lines,
            new_text_lines,
            fromfile="old_capture",
            tofile="new_capture",
            lineterm="",
            n=context,
        )
    )

    hunks, summary = _compute_changes(old_lines, new_lines)
    return DiffResult(
        schema_version="2026-03-29",
        changed=bool(hunks),
        summary=summary,
        documents={
            "old": {"pages": 1, "lines": len(old_lines)},
            "new": {"pages": 1, "lines": len(new_lines)},
        },
        unified_diff=patch,
        hunks=hunks,
        changes=hunks,
    )


def _flatten_pages(pages: list[str]) -> list[LineRef]:
    lines: list[LineRef] = []
    global_line = 1

    for page_number, page in enumerate(pages, start=1):
        page_lines = page.splitlines()
        for line_on_page, line_text in enumerate(page_lines, start=1):
            lines.append(
                LineRef(
                    global_line=global_line,
                    page=page_number,
                    line_on_page=line_on_page,
                    text=line_text,
                )
            )
            global_line += 1

    return lines


def diff_pdf_bytes(old_pdf: PdfInput, new_pdf: PdfInput, context: int = 3) -> DiffResult:
    old_pages = extract_pdf_text(old_pdf)
    new_pages = extract_pdf_text(new_pdf)

    old_lines = _flatten_pages(old_pages)
    new_lines = _flatten_pages(new_pages)
    old_text = [line.text for line in old_lines]
    new_text = [line.text for line in new_lines]

    patch = "\n".join(
        unified_diff(
            old_text,
            new_text,
            fromfile="old_capture",
            tofile="new_capture",
            lineterm="",
            n=context,
        )
    )

    hunks, summary = _compute_changes(old_lines, new_lines)
    return DiffResult(
        schema_version="2026-03-29",
        changed=bool(hunks),
        summary=summary,
        documents={
            "old": {"pages": len(old_pages), "lines": len(old_lines)},
            "new": {"pages": len(new_pages), "lines": len(new_lines)},
        },
        unified_diff=patch,
        hunks=hunks,
        changes=hunks,
    )


def diff_pdf_files(old_pdf_path: str | Path, new_pdf_path: str | Path, context: int = 3) -> DiffResult:
    return diff_pdf_bytes(old_pdf_path, new_pdf_path, context=context)
