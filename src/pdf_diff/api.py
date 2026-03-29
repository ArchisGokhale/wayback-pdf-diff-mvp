from __future__ import annotations

from fastapi import FastAPI, File, Form, UploadFile

from .diff_engine import diff_pdf_bytes

app = FastAPI(title="Wayback PDF Diff MVP", version="0.1.0")


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/diff/pdf")
async def diff_pdf_endpoint(
    old_capture: UploadFile = File(...),
    new_capture: UploadFile = File(...),
    context: int = Form(3),
) -> dict:
    old_data = await old_capture.read()
    new_data = await new_capture.read()

    result = diff_pdf_bytes(old_data, new_data, context=context)
    return result.as_dict()
