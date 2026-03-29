# Wayback PDF Diff

A complete backend-oriented project for comparing two PDF captures and returning structured, page-aware diffs with quality metrics, async job execution, and simple browser rendering.

Built as a practical contribution base for the Internet Archive Wayback PDF Changes effort.

## Implemented Features

- PDF extraction pipeline with normalized text output
- Optional OCR fallback hooks for low-text pages
- Two diff granularities:
  - `line`
  - `block` (paragraph-like grouped chunks)
- Move detection heuristic (`delete + insert` -> `move` when similar)
- Versioned API response contract
- Extraction quality and runtime metrics
- Async batch job API with in-memory queue/status
- JSON schema endpoint and saved schema file
- Browser viewer and HTML render endpoint
- CLI for local compare/export workflows
- Dockerfile and GitHub Actions CI
- Full automated test suite

## Project Layout

- `src/pdf_diff/extractor.py`: extraction, OCR hooks, quality metrics
- `src/pdf_diff/diff_engine.py`: diff core, granularity, move detection, metrics
- `src/pdf_diff/api.py`: sync diff API, async jobs API, schema endpoint, viewer
- `src/pdf_diff/cli.py`: command-line compare utility
- `docs/diff-response.schema.json`: response contract artifact
- `main.py`: root API entrypoint
- `.github/workflows/ci.yml`: CI test workflow
- `Dockerfile`: container runtime

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

- API docs: `http://127.0.0.1:8000/docs`
- Viewer: `http://127.0.0.1:8000/viewer`
- Health: `GET /health`

## Core Endpoints

1. `POST /api/v1/diff/pdf`
  - Inputs: `old_capture`, `new_capture`, `context`, `granularity`, `enable_ocr`
  - Returns: full diff payload with hunks, quality, timing, and summary

2. `POST /api/v1/jobs/diff/pdf`
  - Queues diff work in background
  - Returns `job_id`

3. `GET /api/v1/jobs/{job_id}`
  - Poll status: `queued`, `running`, `completed`, `failed`

4. `GET /api/v1/schema/diff/pdf`
  - Returns JSON schema for response contract

5. `POST /api/v1/render/html`
  - Returns a simple HTML diff page

## CLI

```powershell
.\.venv\Scripts\python.exe pdf_diff_cli.py old.pdf new.pdf --granularity block --out diff.json
```

Options:

- `--context N`
- `--granularity line|block`
- `--enable-ocr`
- `--out path.json`

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Docker

```powershell
docker build -t wayback-pdf-diff .
docker run --rm -p 8000:8000 wayback-pdf-diff
```

## OCR Notes

OCR is optional and only activated when `enable_ocr=true`.

For local OCR support, install:

- Python packages: `pytesseract`, `pdf2image`
- System tools: Tesseract OCR and Poppler

If OCR dependencies are missing, the API still works and reports OCR warnings in `extraction_quality`.

## Contributing

1. Create a feature branch
2. Add tests for behavior changes
3. Run `pytest` before pushing
4. Open PR with clear expected behavior and sample payload
