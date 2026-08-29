# ST7071CEM Information Retrieval Assignment

Two tasks, served by one application:

1. **A vertical search engine** over publications by Coventry University's
   Centre for Healthcare and Community Transformation (CHCT).
2. **A document clustering system** that sorts news articles into Economics,
   Entertainment and Politics.

The index, the ranking and the persistence are written from scratch. The only
thing the two tasks share is the text analyzer, so that a word means the same
on both sides.

## Quick start

You need Python 3.14, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and Node 22+ if you want to rebuild the frontend.

```bash
uv sync                            # install
uv run ir-cluster                  # fit Task 2, about 30 seconds
uv run uvicorn api.main:app --reload
```

Open <http://localhost:8000>. The nav bar switches between the two tasks.

That is everything. The crawled corpus and the search index are committed, so
nothing above touches the network or crawls a live university server.

<details>
<summary><b>Rebuilding the frontend</b></summary>

The React app is built separately and FastAPI serves the result from
`frontend/dist`.

```bash
cd frontend
npm install
npm run dev     # development on :5173, proxies /api to :8000
npm run build   # production build, written to frontend/dist
```

</details>

<details>
<summary><b>Repository layout</b></summary>

```
src/
  miniseek/       Search library written from scratch: analyzer, inverted
                  index, scorers, persistence
  crawler/        Task 1: collects publications from the research portal
  publications/   The schema both sides agree on, and where it is stored
  clustering/     Task 2: corpus, k-means model, evaluation
  api/            FastAPI routes for both tasks, and the app itself
tests/            165 tests, none of which touch the network
frontend/         React and Tailwind interface for both tasks
data/             Crawls, the built index, and input data
outputs/          Generated files, all rebuildable
typesense/        Docker Compose bench comparing miniseek to a real engine
```

Each package stands on its own. Collecting, indexing and clustering are
separate concerns.

</details>

## Task 1: Vertical search engine

Search over CHCT publications. Results are ranked, and every author with a
pureportal profile links to a page listing everything they wrote.

The corpus is already committed, so you only need the commands below if you
want to collect it again yourself.

### Crawling

```bash
uv run ir-crawl --once           # a full crawl, ~20 minutes at polite pace
uv run ir-crawl --status         # when it last ran
```

It obeys `robots.txt` and the 5 second crawl delay the portal asks for, and
uses conditional requests so a repeat crawl is cheap. Each run is written to
its own folder under `data/crawls/`.

<details>
<summary><b>More crawler options</b></summary>

```bash
uv run ir-crawl --once --limit 5               # a quick sample instead
uv run ir-crawl --once --limit 5 --skip-delay  # same, without the crawl delay
uv run ir-crawl --schedule                     # weekly, as the brief asks
uv run ir-crawl --schedule 1week               # same, written out explicitly
uv run ir-crawl --schedule 1month              # monthly instead
uv run ir-crawl --schedule 3months             # every 3 months instead
uv run ir-crawl --schedule 1min --limit 5      # exercise the schedule loop fast
```

Console logging goes to stderr, so redirecting into a file needs `2>&1` (a
plain `| tee file.log` only captures stdout and silently misses it):

```bash
uv run ir-crawl --once 2>&1 | tee logs/full-crawl.log
```

[`src/crawler/README.md`](src/crawler/README.md) covers the collection side on
its own, including how it stays polite and one bug that made it silently
believe it was banned from the whole site.

</details>

### Indexing

A crawl only collects documents. Building the searchable index from them is a
separate step, and it is fast because it never touches the network:

```bash
uv run ir-index                                   # index the newest crawl
uv run ir-index --crawl 2026-08-29-12-35-06-NPT   # index a specific crawl
```

Crawl ids are the folder names under `data/crawls/`; list them with
`ls data/crawls/`. Rebuilding is the normal case, so `ir-index` replaces the
index rather than adding to it.

<details>
<summary><b>More indexing options</b></summary>

```bash
uv run ir-index --append              # add to the existing index, don't rebuild
uv run ir-index --index-dir path/     # write the index somewhere else
uv run ir-index --crawls-dir path/    # read crawls from somewhere else
uv run ir-index -v                    # verbose
```

Because the documents are stored and the index is derived from them, a change
to the analyzer is applied by re-running `ir-index`. There is no need to crawl
the site again.

</details>

### Looking inside the index

```bash
uv run miniseek-view data/index    # counts, settings, and the documents
uv run ir-bm25                     # checks BM25 against the formula worked by hand
```

`miniseek-view` opens a small read-only viewer in the browser, the equivalent
of a collection browser for a real search engine.

<details>
<summary><b>Comparing against Typesense</b></summary>

`miniseek` is shaped after [Typesense](https://typesense.org), so
[`typesense/`](typesense/) runs a real one on the same corpus and puts the two
side by side. It is a bench, not a component: nothing in `src/` imports it and
nothing breaks when the container is down.

```bash
cd typesense && docker compose up -d      # Typesense on :8108, dashboard on :8109
cd .. && uv run python typesense/load.py  # same corpus, same field weights

uv run python typesense/compare.py           # a fixed set of queries
uv run python typesense/compare.py --typo    # misspellings, which only Typesense answers
```

Typesense has no UI of its own, so the compose file also runs the community
dashboard at <http://localhost:8109>. Log in with the API key `localdev`; the
host and port are already filled in.

[`typesense/README.md`](typesense/README.md) covers how the two schemas are
matched up, and why the scores must not be compared directly even though the
orderings can be.

</details>

## Task 2: Document clustering

BBC News articles grouped into Economics, Entertainment and Politics by k-means
over TF-IDF vectors. New unseen text can be assigned to a cluster from the
interface.

600 articles, 200 per category, k=3. Adjusted Rand Index 0.907, and 96.8% of
articles land in the cluster matching their true category.

```bash
uv run ir-cluster                     # 200 per category
uv run ir-cluster --all               # every article
uv run ir-cluster --per-category 100
```

<details>
<summary><b>About the corpus</b></summary>

The BBC corpus is not committed. It downloads on first run from
<http://mlg.ucd.ie/files/datasets/bbc-fulltext.zip> and is cached afterwards.
It remains BBC copyright, used here for non-commercial coursework with
attribution, which is what its terms allow.

[`src/clustering/README.md`](src/clustering/README.md) covers this task on its
own: where the corpus is downloaded to, how the model is built and loaded, how
k was chosen, and why one preprocessing setting mattered more than the
algorithm did.

</details>

## Tests

```bash
uv run pytest
uv run ruff check src tests
uv run ty check src tests
```

165 tests. The crawler tests use a stand-in fetcher and the clustering tests
use a fixture, so the suite runs offline and never hits a real server.

## Licence

MIT, see [LICENSE](LICENSE). That covers the code only. The crawled
publication metadata belongs to its publishers, and the BBC corpus keeps its
own terms, described under Task 2.
