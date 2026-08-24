# ST7071CEM Information Retrieval Assignment

Two tasks, served by one application.

```
src/
  miniseek/       Search library written from scratch: analyzer, inverted
                  index, scorers, persistence
  crawler/        Task 1: collects publications from the research portal
  publications/   The schema both sides agree on, and where it is stored
  clustering/     Task 2: corpus, k-means model, evaluation
  api/            FastAPI routes for both tasks, and the app itself
tests/            141 tests, none of which touch the network
frontend/         React and Tailwind interface for both tasks
data/             Input data
outputs/          Generated files, all rebuildable
```

Each package stands on its own. Collecting, indexing and clustering are
separate concerns, and the only thing the two tasks share is the text analyzer
in `miniseek`, so that a term means the same in both.

## Getting started

Needs Python 3.14 and [uv](https://docs.astral.sh/uv/getting-started/installation/),
plus Node 22 or later for the frontend.

```bash
uv sync
uv run ir-cluster                 # fit Task 2, about 30 seconds
uv run uvicorn api.main:app --reload
```

Open <http://localhost:8000>. The nav bar switches between the two tasks.

The frontend is built separately, and FastAPI serves the result:

```bash
cd frontend
npm install
npm run dev     # development on :5173, proxies /api to :8000
npm run build   # production, written to frontend/dist
```

## Task 1: Vertical search engine

A search engine over publications by members of Coventry University's Centre
for Healthcare and Community Transformation. Results are ranked, and every
author links to a page listing everything they wrote.

The crawler obeys `robots.txt` and the 5 second crawl delay the portal asks
for, uses conditional requests so a repeat crawl is cheap, and can run on the
weekly schedule the brief describes.

The index, the ranking and the persistence layer are written from scratch in
`miniseek` rather than taken from a library. Two scorers are implemented so
they can be compared on the same data: BM25 and TF-IDF with cosine similarity.

```bash
uv run ir-crawl --once                       # ~35-40 minutes, polite pacing
uv run ir-crawl --once --limit 5             # a quick sample instead
uv run ir-crawl --schedule                   # weekly, as the brief asks
uv run ir-crawl --schedule 1min --limit 5    # exercise the schedule loop fast
uv run ir-crawl --status                     # when it last ran
uv run ir-bm25                               # checks BM25 against the formula worked by hand
```

[`src/crawler/README.md`](src/crawler/README.md) covers the collection side on
its own, including how it stays polite and one bug that made it silently
believe it was banned from the whole site.

The crawled corpus is committed, so the search engine works on a fresh
checkout without crawling a live university server again.

## Task 2: Document clustering

BBC News articles grouped into Economics, Entertainment and Politics by
k-means over TF-IDF vectors, with new unseen text assigned to a cluster from
the interface.

600 articles, 200 per category, k=3. Adjusted Rand Index 0.907, and 96.8% of
articles land in the cluster matching their true category.

```bash
uv run ir-cluster                     # 200 per category
uv run ir-cluster --all               # every article
uv run ir-cluster --per-category 100
```

[`src/clustering/README.md`](src/clustering/README.md) covers this task on its
own: where the corpus is downloaded to, how the model is built and loaded, how
k was chosen, and why one preprocessing setting mattered more than the
algorithm did.

The BBC corpus is not committed. It downloads on first run from
<http://mlg.ucd.ie/files/datasets/bbc-fulltext.zip> and is cached. It remains
BBC copyright, used here for non-commercial coursework with attribution, which
is what its terms allow.

## Tests

```bash
uv run pytest
uv run ruff check src tests
uv run ty check src tests
```

141 tests. The crawler tests use a stand-in fetcher and the clustering tests
use a fixture, so the suite runs offline and never hits a real server.

## Licence

MIT, see [LICENSE](LICENSE). That covers the code only. The crawled
publication metadata belongs to its publishers, and the BBC corpus keeps its
own terms, described under Task 2.
