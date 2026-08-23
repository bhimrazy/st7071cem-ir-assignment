# Backend

FastAPI application serving both coursework tasks.

```
src/
  miniseek/          Search library written from scratch
  ir_search_engine/  Task 1: polite crawler, publication schema
  clustering/        Task 2: corpus, k-means, evaluation
  api/               Routes for both tasks, and the app
scripts/             Command line entry points
tests/               133 tests, no network access needed
```

```bash
uv sync
uv run python scripts/run_clustering.py   # fit Task 2
uv run python scripts/crawl.py --once     # crawl for Task 1
uv run uvicorn api.main:app --reload
uv run pytest
```

Data is read from `data/` and generated files are written to `outputs/`.
Both can be relocated with `IR_DATA_DIR` and `IR_OUTPUT_DIR`.
