from io import BytesIO

from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from pdf_diff.api import app


client = TestClient(app)


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


def test_healthcheck() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_pdf_diff_endpoint() -> None:
    old_pdf = make_pdf_bytes(["Original", "Content"])
    new_pdf = make_pdf_bytes(["Original", "Updated"])

    response = client.post(
        "/api/v1/diff/pdf",
        files={
            "old_capture": ("old.pdf", old_pdf, "application/pdf"),
            "new_capture": ("new.pdf", new_pdf, "application/pdf"),
        },
        data={"context": "2"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["changed"] is True
    assert payload["schema_version"] == "2026-03-29"
    assert payload["summary"]["lines_added"] >= 1
    assert payload["summary"]["lines_removed"] >= 1
    assert len(payload["hunks"]) >= 1
    assert "page" in payload["hunks"][0]["old"]["lines"][0]
