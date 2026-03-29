from __future__ import annotations

from dataclasses import dataclass
import importlib
from io import BytesIO
from pathlib import Path
from typing import Any, Union, cast

from pypdf import PdfReader

PdfInput = Union[bytes, bytearray, str, Path]


@dataclass
class ExtractionResult:
    pages: list[str]
    metrics: dict[str, Any]


def _normalize_line(line: str) -> str:
    return " ".join(line.strip().split())


def _ensure_pdf_bytes(pdf_input: PdfInput) -> bytes:
    if isinstance(pdf_input, (bytes, bytearray)):
        return bytes(pdf_input)
    if not isinstance(pdf_input, (str, Path)):
        raise TypeError("pdf_input must be bytes or a valid path")
    path = Path(cast(str | Path, pdf_input))
    return path.read_bytes()


def _ocr_page_text(pdf_bytes: bytes, page_number: int) -> tuple[str, str | None]:
    try:
        convert_module = importlib.import_module("pdf2image")
        tesseract_module = importlib.import_module("pytesseract")
    except Exception:
        return "", "optional-ocr-dependencies-missing"

    try:
        convert_from_bytes = getattr(convert_module, "convert_from_bytes")
        image_to_string = getattr(tesseract_module, "image_to_string")
        images = convert_from_bytes(pdf_bytes, first_page=page_number, last_page=page_number)
        if not images:
            return "", "ocr-image-conversion-empty"
        text = image_to_string(images[0])
        return text or "", None
    except Exception as exc:
        return "", f"ocr-failed:{exc}"


def extract_pdf_content(pdf_input: PdfInput, enable_ocr: bool = False) -> ExtractionResult:
    """Extract normalized text and quality metrics from each page of a PDF."""
    pdf_bytes = _ensure_pdf_bytes(pdf_input)
    reader = PdfReader(BytesIO(pdf_bytes))

    pages: list[str] = []
    pages_with_text = 0
    pages_without_text = 0
    chars_extracted = 0
    ocr_used = 0
    warnings: list[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        raw_text = page.extract_text() or ""
        normalized_lines = [_normalize_line(line) for line in raw_text.splitlines()]
        clean_page = "\n".join(line for line in normalized_lines if line)

        if not clean_page and enable_ocr:
            ocr_text, warning = _ocr_page_text(pdf_bytes, page_number)
            if warning:
                warnings.append(f"page-{page_number}:{warning}")
            if ocr_text:
                normalized_lines = [_normalize_line(line) for line in ocr_text.splitlines()]
                clean_page = "\n".join(line for line in normalized_lines if line)
                if clean_page:
                    ocr_used += 1

        if clean_page:
            pages_with_text += 1
            chars_extracted += len(clean_page)
        else:
            pages_without_text += 1

        pages.append(clean_page)

    total_pages = len(pages)
    metrics: dict[str, Any] = {
        "pages_total": total_pages,
        "pages_with_text": pages_with_text,
        "pages_without_text": pages_without_text,
        "chars_extracted": chars_extracted,
        "avg_chars_per_text_page": round(chars_extracted / pages_with_text, 2) if pages_with_text else 0.0,
        "text_coverage_ratio": round((pages_with_text / total_pages), 3) if total_pages else 0.0,
        "ocr_requested": enable_ocr,
        "ocr_used_pages": ocr_used,
        "warnings": warnings,
    }
    return ExtractionResult(pages=pages, metrics=metrics)


def extract_pdf_text(pdf_input: PdfInput) -> list[str]:
    """Extract page text from a PDF and normalize whitespace per line."""
    return extract_pdf_content(pdf_input).pages
