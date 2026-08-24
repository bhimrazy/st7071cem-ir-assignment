from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("IR_DATA_DIR", PROJECT_ROOT / "data"))
# One directory per crawl, kept so a corpus can be rebuilt or compared later.
CRAWLS_DIR = DATA_DIR / "crawls"
# Derived from a crawl by `ir-index`, and disposable.
INDEX_DIR = DATA_DIR / "index"
