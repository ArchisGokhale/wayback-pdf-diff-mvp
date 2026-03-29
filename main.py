from pathlib import Path
import sys

# Allow running `uvicorn main:app` from the repository root.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pdf_diff.api import app  # noqa: E402
