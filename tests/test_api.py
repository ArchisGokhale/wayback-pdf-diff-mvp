from io import BytesIO
from time import sleep

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


def test_schema_endpoint() -> None:
    response = client.get("/api/v1/schema/diff/pdf")
    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "PDF Diff Response"


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
    assert payload["metrics"]["granularity"] == "line"


def test_pdf_diff_endpoint_rejects_invalid_pdf() -> None:
    response = client.post(
        "/api/v1/diff/pdf",
        files={
            "old_capture": ("old.pdf", b"not-a-real-pdf", "application/pdf"),
            "new_capture": ("new.pdf", b"also-not-a-real-pdf", "application/pdf"),
        },
        data={"context": "2"},
    )

    assert response.status_code == 400
    assert "Invalid PDF input" in response.json()["detail"]


def test_pdf_diff_endpoint_validates_context_range() -> None:
    old_pdf = make_pdf_bytes(["Original", "Content"])
    new_pdf = make_pdf_bytes(["Original", "Updated"])

    response = client.post(
        "/api/v1/diff/pdf",
        files={
            "old_capture": ("old.pdf", old_pdf, "application/pdf"),
            "new_capture": ("new.pdf", new_pdf, "application/pdf"),
        },
        data={"context": "999"},
    )

    assert response.status_code == 422


def test_pdf_diff_endpoint_block_granularity() -> None:
    old_pdf = make_pdf_bytes(["One", "Two", "Three", "Four"])
    new_pdf = make_pdf_bytes(["One", "Two", "Three", "Five"])

    response = client.post(
        "/api/v1/diff/pdf",
        files={
            "old_capture": ("old.pdf", old_pdf, "application/pdf"),
            "new_capture": ("new.pdf", new_pdf, "application/pdf"),
        },
        data={"context": "2", "granularity": "block"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["granularity"] == "block"


def test_jobs_endpoint_runs_to_completion() -> None:
    old_pdf = make_pdf_bytes(["Original", "Content"])
    new_pdf = make_pdf_bytes(["Original", "Updated"])

    create_response = client.post(
        "/api/v1/jobs/diff/pdf",
        files={
            "old_capture": ("old.pdf", old_pdf, "application/pdf"),
            "new_capture": ("new.pdf", new_pdf, "application/pdf"),
        },
        data={"context": "2", "granularity": "line"},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["job_id"]

    payload = None
    for _ in range(20):
        job_response = client.get(f"/api/v1/jobs/{job_id}")
        assert job_response.status_code == 200
        payload = job_response.json()
        if payload["status"] in {"completed", "failed"}:
            break
        sleep(0.05)

    assert payload is not None
    assert payload["status"] == "completed"
    assert payload["result"]["changed"] is True
