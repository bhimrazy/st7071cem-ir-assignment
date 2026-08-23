"""Where the clustering task reads its input and writes its output.

Separated so the `parents[...]` walk to the project root lives in one place,
and so inputs (the corpus we downloaded) stay distinct from outputs (the
model and figures we produced, which are regenerable).
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("IR_DATA_DIR", PROJECT_ROOT / "data")) / "clustering"
OUTPUT_DIR = (
    Path(os.environ.get("IR_OUTPUT_DIR", PROJECT_ROOT / "outputs")) / "clustering"
)

CORPUS_PATH = DATA_DIR / "bbc-fulltext.zip"
MODEL_PATH = OUTPUT_DIR / "kmeans_model.pkl"
REPORT_PATH = OUTPUT_DIR / "clustering_report.json"
FIGURES_DIR = OUTPUT_DIR / "figures"
