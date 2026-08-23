# ST7071CEM Information Retrieval Assignment

Two tasks, one application.

**Task 1** is a vertical search engine over publications by members of Coventry
University's Centre for Healthcare and Community Transformation. It crawls the
university's research portal politely, builds an inverted index from scratch,
and ranks results with BM25 or TF-IDF.

**Task 2** is a document clustering system. It groups BBC News articles into
Economics, Entertainment and Politics with k-means, and assigns new text the
model has never seen to one of those clusters.

## Layout

```
src/
  miniseek/          Search library written from scratch: analyzer,
                     inverted index, scorers, persistence
  ir_search_engine/  Task 1: the polite crawler and the publication schema
  clustering/        Task 2: corpus, k-means model, evaluation (see its README)
  api/               FastAPI routes for both tasks, and the app itself
scripts/             Command line entry points
tests/               133 tests, no network access required
frontend/            React and Tailwind interface for both tasks
data/                Input data
outputs/             Generated files, all rebuildable
```

The two tasks are separate packages. They share exactly one thing, the text
analyzer, so that a term means the same thing in both.

## Running it

```bash
uv sync

# Task 2: fit the clustering model (downloads the BBC corpus on first run)
uv run python scripts/run_clustering.py

# Task 1: crawl the portal (about 7 minutes, obeys a 5 second crawl delay)
uv run python scripts/crawl.py --once
# or run it on the weekly schedule the brief asks for
uv run python scripts/crawl.py --schedule

# serve both tasks
uv run uvicorn api.main:app --reload
```

Then open <http://localhost:8000>. The frontend is built separately:

```bash
cd frontend
npm install
npm run dev     # development, proxies /api to the backend
npm run build   # production, served by FastAPI from frontend/dist
```

## Other commands

```bash
uv run pytest                                  # the test suite
uv run python scripts/crawl.py --status        # when the crawler last ran
uv run python scripts/bm25_worked_example.py   # checks the BM25 numbers in the docs by hand
```

## Notes on the data

The crawled publication corpus is committed, because crawling it again means
seven minutes of requests to a live university server for no new information.

The BBC corpus is not committed. It is downloaded from
<http://mlg.ucd.ie/files/datasets/bbc-fulltext.zip> on first run and cached.
It remains BBC copyright and is used here for non-commercial coursework with
attribution, which is what its terms allow.

## Reading further

- [`LEARNING.md`](LEARNING.md) is a step by step build log, written as each
  piece was built rather than afterwards.
- [`src/clustering/README.md`](src/clustering/README.md)
  covers Task 2 on its own.
- [`docs/bm25.md`](docs/bm25.md) is a deep dive on the ranking function, with a
  worked example that a script checks.
