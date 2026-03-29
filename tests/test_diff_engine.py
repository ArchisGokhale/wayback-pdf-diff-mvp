from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from pdf_diff.diff_engine import diff_pdf_bytes, diff_text


def make_pdf_bytes(lines: list[str]) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    y = 760
    for line in lines:
        c.drawString(72, y, line)
        y -= 16
    c.showPage()
    c.save()
    return buffer.getvalue()


def make_pdf_bytes_pages(pages: list[list[str]]) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    for page_lines in pages:
        y = 760
        for line in page_lines:
            c.drawString(72, y, line)
            y -= 16
        c.showPage()
    c.save()
    return buffer.getvalue()


def test_diff_text_detects_change() -> None:
    result = diff_text("alpha\nbeta", "alpha\ngamma")
    assert result.changed is True
    assert result.schema_version == "2026-03-29"
    assert result.summary.lines_added == 1
    assert result.summary.lines_removed == 1


def test_diff_pdf_bytes_detects_change() -> None:
    old_pdf = make_pdf_bytes(["Line A", "Line B"])
    new_pdf = make_pdf_bytes(["Line A", "Line C"])

    result = diff_pdf_bytes(old_pdf, new_pdf)

    assert result.changed is True
    assert "Line B" in result.unified_diff
    assert "Line C" in result.unified_diff
    assert result.documents["old"]["pages"] == 1
    assert result.documents["new"]["pages"] == 1


def test_diff_pdf_bytes_includes_page_aware_lines() -> None:
    old_pdf = make_pdf_bytes_pages([["Same"], ["Line B"]])
    new_pdf = make_pdf_bytes_pages([["Same"], ["Line C"]])

    result = diff_pdf_bytes(old_pdf, new_pdf)

    assert result.changed is True
    assert len(result.hunks) >= 1
    first_hunk = result.hunks[0]

    assert first_hunk["old"]["lines"][0]["page"] == 2
    assert first_hunk["new"]["lines"][0]["page"] == 2
    assert first_hunk["old"]["lines"][0]["line_on_page"] == 1
    assert first_hunk["new"]["lines"][0]["line_on_page"] == 1
