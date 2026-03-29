from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from threading import Lock
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pypdf.errors import PdfReadError

from .diff_engine import diff_pdf_bytes

app = FastAPI(title="Wayback PDF Diff MVP", version="0.1.0")

_JOBS: dict[str, dict] = {}
_JOBS_LOCK = Lock()


def _utcnow() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _run_job(job_id: str, old_data: bytes, new_data: bytes, context: int, granularity: str, enable_ocr: bool) -> None:
    with _JOBS_LOCK:
        _JOBS[job_id]["status"] = "running"
        _JOBS[job_id]["started_at"] = _utcnow()

    try:
        result = diff_pdf_bytes(old_data, new_data, context=context, granularity=granularity, enable_ocr=enable_ocr)
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "completed"
            _JOBS[job_id]["result"] = result.as_dict()
            _JOBS[job_id]["finished_at"] = _utcnow()
    except Exception as exc:  # pragma: no cover - unexpected failure path
        with _JOBS_LOCK:
            _JOBS[job_id]["status"] = "failed"
            _JOBS[job_id]["error"] = str(exc)
            _JOBS[job_id]["finished_at"] = _utcnow()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/schema/diff/pdf")
def diff_schema() -> dict:
        return {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": "PDF Diff Response",
                "type": "object",
                "required": ["schema_version", "changed", "summary", "documents", "unified_diff", "hunks"],
                "properties": {
                        "schema_version": {"type": "string"},
                        "changed": {"type": "boolean"},
                        "summary": {
                                "type": "object",
                                "required": ["lines_added", "lines_removed", "lines_changed"],
                                "properties": {
                                        "lines_added": {"type": "integer"},
                                        "lines_removed": {"type": "integer"},
                                        "lines_changed": {"type": "integer"},
                                },
                        },
                        "documents": {"type": "object"},
                        "extraction_quality": {"type": "object"},
                        "metrics": {"type": "object"},
                        "unified_diff": {"type": "string"},
                        "hunks": {"type": "array", "items": {"type": "object"}},
                        "changes": {"type": "array", "items": {"type": "object"}},
                },
        }


@app.get("/viewer", response_class=HTMLResponse)
def viewer() -> str:
        return """
<!doctype html>
<html>
<head>
    <meta charset='utf-8' />
    <meta name='viewport' content='width=device-width,initial-scale=1' />
    <title>PDF Diff Viewer</title>
    <style>
        body { font-family: Segoe UI, sans-serif; margin: 24px; background: #f3f5f7; color: #111; }
        .card { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 8px 24px rgba(0,0,0,.08); }
        .row { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
        .col { flex: 1; min-width: 240px; }
        button { border: none; background: #0a66c2; color: #fff; padding: 10px 14px; border-radius: 8px; cursor: pointer; }
        pre { background: #0e1116; color: #d7e0ea; padding: 12px; border-radius: 8px; overflow: auto; }
        .summary { margin: 10px 0; }
    </style>
</head>
<body>
    <div class='card'>
        <h2>Wayback PDF Diff Viewer</h2>
        <div class='row'>
            <div class='col'><input id='old' type='file' accept='application/pdf' /></div>
            <div class='col'><input id='new' type='file' accept='application/pdf' /></div>
            <div class='col'>
                <select id='granularity'>
                    <option value='line'>line</option>
                    <option value='block'>block</option>
                </select>
            </div>
        </div>
        <button onclick='runDiff()'>Compare</button>
        <div class='summary' id='summary'></div>
        <pre id='patch'></pre>
    </div>
    <script>
        async function runDiff() {
            const oldFile = document.getElementById('old').files[0];
            const newFile = document.getElementById('new').files[0];
            if (!oldFile || !newFile) { alert('Select both PDF files.'); return; }
            const fd = new FormData();
            fd.append('old_capture', oldFile);
            fd.append('new_capture', newFile);
            fd.append('context', '3');
            fd.append('granularity', document.getElementById('granularity').value);
            const resp = await fetch('/api/v1/diff/pdf', { method: 'POST', body: fd });
            const data = await resp.json();
            document.getElementById('summary').textContent =
                `changed=${data.changed} added=${data.summary.lines_added} removed=${data.summary.lines_removed} changed=${data.summary.lines_changed}`;
            document.getElementById('patch').textContent = data.unified_diff || '';
        }
    </script>
</body>
</html>
"""


@app.post("/api/v1/render/html", response_class=HTMLResponse)
async def render_html(
        old_capture: UploadFile = File(...),
        new_capture: UploadFile = File(...),
        context: int = Form(3, ge=0, le=20),
        granularity: str = Form("line"),
) -> str:
        old_data = await old_capture.read()
        new_data = await new_capture.read()
        result = diff_pdf_bytes(old_data, new_data, context=context, granularity=granularity)

        header = f"<h3>Changed: {result.changed} | Added: {result.summary.lines_added} | Removed: {result.summary.lines_removed}</h3>"
        patch = f"<pre>{escape(result.unified_diff)}</pre>"
        return f"<html><body>{header}{patch}</body></html>"


@app.post("/api/v1/diff/pdf")
async def diff_pdf_endpoint(
    old_capture: UploadFile = File(...),
    new_capture: UploadFile = File(...),
    context: int = Form(3, ge=0, le=20),
    granularity: str = Form("line"),
    enable_ocr: bool = Form(False),
) -> dict:
    old_data = await old_capture.read()
    new_data = await new_capture.read()

    if not old_data or not new_data:
        raise HTTPException(status_code=400, detail="Both PDF files are required and must be non-empty.")

    if granularity not in {"line", "block"}:
        raise HTTPException(status_code=400, detail="granularity must be one of: line, block")

    try:
        result = diff_pdf_bytes(old_data, new_data, context=context, granularity=granularity, enable_ocr=enable_ocr)
    except PdfReadError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid PDF input: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result.as_dict()


@app.post("/api/v1/jobs/diff/pdf")
async def create_diff_job(
    background_tasks: BackgroundTasks,
    old_capture: UploadFile = File(...),
    new_capture: UploadFile = File(...),
    context: int = Form(3, ge=0, le=20),
    granularity: str = Form("line"),
    enable_ocr: bool = Form(False),
) -> dict:
    old_data = await old_capture.read()
    new_data = await new_capture.read()

    if not old_data or not new_data:
        raise HTTPException(status_code=400, detail="Both PDF files are required and must be non-empty.")
    if granularity not in {"line", "block"}:
        raise HTTPException(status_code=400, detail="granularity must be one of: line, block")

    job_id = str(uuid4())
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "status": "queued",
            "created_at": _utcnow(),
            "result": None,
            "error": None,
        }

    background_tasks.add_task(_run_job, job_id, old_data, new_data, context, granularity, enable_ocr)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, **job}
