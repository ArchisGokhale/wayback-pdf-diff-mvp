from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Union

from pypdf import PdfReader

PdfInput = Union[bytes, bytearray, str, Path]


def _normalize_line(line: str) -> str:
    return " ".join(line.strip().split())


def extract_pdf_text(pdf_input: PdfInput) -> list[str]:
    """Extract page text from a PDF and normalize whitespace per line."""
    if isinstance(pdf_input, (bytes, bytearray)):
        reader = PdfReader(BytesIO(pdf_input))
    else:
        reader = PdfReader(str(pdf_input))

    pages: list[str] = []
    for page in reader.pages:
        raw_text = page.extract_text() or ""
        normalized_lines = [_normalize_line(line) for line in raw_text.splitlines()]
        # Keep non-empty lines only to reduce layout noise.
        clean_page = "\n".join(line for line in normalized_lines if line)
        pages.append(clean_page)

    return pages
