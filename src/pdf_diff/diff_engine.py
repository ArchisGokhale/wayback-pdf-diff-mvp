from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher, unified_diff
from pathlib import Path
from time import perf_counter
from typing import Any

from .extractor import PdfInput, extract_pdf_content


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
    extraction_quality: dict[str, Any]
    metrics: dict[str, Any]
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


def _detect_moves(hunks: list[dict[str, Any]]) -> None:
    deletes: list[dict[str, Any]] = [h for h in hunks if h["op"] == "delete" and h["old"]["lines"]]
    inserts: list[dict[str, Any]] = [h for h in hunks if h["op"] == "insert" and h["new"]["lines"]]

    for delete_hunk in deletes:
        old_text = "\n".join(line["text"] for line in delete_hunk["old"]["lines"])
        best_insert: dict[str, Any] | None = None
        best_score = 0.0

        for insert_hunk in inserts:
            if insert_hunk.get("_paired"):
                continue
            new_text = "\n".join(line["text"] for line in insert_hunk["new"]["lines"])
            score = SequenceMatcher(a=old_text, b=new_text).ratio()
            if score > best_score:
                best_score = score
                best_insert = insert_hunk

        if best_insert is not None and best_score >= 0.85:
            delete_hunk["op"] = "move"
            delete_hunk["moved_to"] = {
                "start": best_insert["new"]["start"],
                "end": best_insert["new"]["end"],
                "similarity": round(best_score, 3),
            }
            best_insert["_paired"] = True

    hunks[:] = [h for h in hunks if not h.get("_paired")]


def _to_blocks(lines: list[LineRef], block_size: int = 3) -> list[LineRef]:
    blocks: list[LineRef] = []
    by_page: dict[int, list[LineRef]] = {}
    for line in lines:
        by_page.setdefault(line.page, []).append(line)

    idx = 1
    for page in sorted(by_page):
        page_lines = by_page[page]
        for start in range(0, len(page_lines), block_size):
            chunk = page_lines[start : start + block_size]
            if not chunk:
                continue
            blocks.append(
                LineRef(
                    global_line=idx,
                    page=page,
                    line_on_page=chunk[0].line_on_page,
                    text=" ".join(part.text for part in chunk),
                )
            )
            idx += 1
    return blocks


def diff_text(old_text: str, new_text: str, context: int = 3, granularity: str = "line") -> DiffResult:
    started = perf_counter()
    old_lines = [
        LineRef(global_line=idx + 1, page=1, line_on_page=idx + 1, text=value)
        for idx, value in enumerate(old_text.splitlines())
    ]
    new_lines = [
        LineRef(global_line=idx + 1, page=1, line_on_page=idx + 1, text=value)
        for idx, value in enumerate(new_text.splitlines())
    ]

    if granularity == "block":
        old_lines = _to_blocks(old_lines)
        new_lines = _to_blocks(new_lines)

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

    diff_started = perf_counter()
    hunks, summary = _compute_changes(old_lines, new_lines)
    _detect_moves(hunks)
    total_ms = round((perf_counter() - started) * 1000, 2)
    diff_ms = round((perf_counter() - diff_started) * 1000, 2)

    return DiffResult(
        schema_version="2026-03-29",
        changed=bool(hunks),
        summary=summary,
        documents={
            "old": {"pages": 1, "lines": len(old_lines)},
            "new": {"pages": 1, "lines": len(new_lines)},
        },
        extraction_quality={"old": {}, "new": {}},
        metrics={"granularity": granularity, "timing_ms": {"extract": 0.0, "diff": diff_ms, "total": total_ms}},
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


def diff_pdf_bytes(
    old_pdf: PdfInput,
    new_pdf: PdfInput,
    context: int = 3,
    granularity: str = "line",
    enable_ocr: bool = False,
) -> DiffResult:
    started = perf_counter()
    old_extract = extract_pdf_content(old_pdf, enable_ocr=enable_ocr)
    new_extract = extract_pdf_content(new_pdf, enable_ocr=enable_ocr)
    old_pages = old_extract.pages
    new_pages = new_extract.pages
    extract_ms = round((perf_counter() - started) * 1000, 2)

    old_lines = _flatten_pages(old_pages)
    new_lines = _flatten_pages(new_pages)

    if granularity == "block":
        old_lines = _to_blocks(old_lines)
        new_lines = _to_blocks(new_lines)

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

    diff_started = perf_counter()
    hunks, summary = _compute_changes(old_lines, new_lines)
    _detect_moves(hunks)
    diff_ms = round((perf_counter() - diff_started) * 1000, 2)
    total_ms = round((perf_counter() - started) * 1000, 2)

    return DiffResult(
        schema_version="2026-03-29",
        changed=bool(hunks),
        summary=summary,
        documents={
            "old": {"pages": len(old_pages), "lines": len(old_lines)},
            "new": {"pages": len(new_pages), "lines": len(new_lines)},
        },
        extraction_quality={"old": old_extract.metrics, "new": new_extract.metrics},
        metrics={
            "granularity": granularity,
            "timing_ms": {"extract": extract_ms, "diff": diff_ms, "total": total_ms},
            "percent_changed": round(
                ((summary.lines_added + summary.lines_removed) / max(len(old_lines), 1)) * 100,
                2,
            ),
        },
        unified_diff=patch,
        hunks=hunks,
        changes=hunks,
    )


def diff_pdf_files(
    old_pdf_path: str | Path,
    new_pdf_path: str | Path,
    context: int = 3,
    granularity: str = "line",
    enable_ocr: bool = False,
) -> DiffResult:
    return diff_pdf_bytes(
        old_pdf_path,
        new_pdf_path,
        context=context,
        granularity=granularity,
        enable_ocr=enable_ocr,
    )
