# Typesense comparison

A local Typesense holding the same 88 publications, so claims about how
`miniseek` compares to a real engine can be checked rather than asserted.

Nothing in `src/` imports this and nothing breaks when the container is down.
It lives outside `src/` for that reason: it is a bench, not a component.

## Running it

```bash
cd typesense && docker compose up -d      # Typesense on 127.0.0.1:8108
cd .. && uv run python typesense/load.py  # create the collection, load the crawl

uv run python typesense/compare.py                      # a fixed set of queries
uv run python typesense/compare.py "mental health"
uv run python typesense/compare.py "mental health" --scorer tf-idf
uv run python typesense/compare.py --typo               # misspelled queries
```

`docker compose down -v` removes the container and its volume.

## Matching the two setups

The comparison is only worth anything if both engines are given the same job,
so the loader mirrors the miniseek schema as closely as Typesense allows.

| miniseek | Typesense | Note |
|---|---|---|
| `Field(weight=3.0)` in the schema | `query_by_weights=3,2,1,1` at query time | Same idea, different place: miniseek fixes weights when the collection is defined, Typesense sets them per query |
| `indexed=False` | `"index": false` | Stored and returned, never searched |
| `id` = the publication URL | `id` = the URL's trailing slug | Typesense puts the id in the URL path of its per-document endpoints, so slashes are a nuisance. The full URL stays in `url` |
| `year` stored as a string, unindexed | `year` as `int32`, faceted | Deliberately *not* matched — it shows the filtering miniseek cannot do at all |
| `authors` as a list of dicts | `authors` as `string[]`, faceted | Only the name is indexed either way |

The default queries are picked to make the two disagree in instructive ways
rather than to flatter either: a plain two-term query, one where miniseek's
stemming collision bites (`community transformation`), one where query
coverage matters (`sleep quality students`), and — under `--typo` — queries
only Typesense can answer at all.

## What it actually showed

Measured on the 88-publication corpus, not predicted.

**The two engines disagree about what a multi-word query means.** miniseek is
OR: a document matching any term is a candidate. Typesense is AND, dropping
terms only when that leaves too few results. The match counts line up exactly:

| Query | miniseek (OR) | docs matching *all* terms | Typesense `found` |
|---|---|---|---|
| `mental health` | 47 | 9 | **9** |
| `diabetes prevention` | 10 | 1 | **1** |
| `sleep quality students` | 18 | 0 | 6 — token dropped, then retried |

This is the same problem `Coordinated` addresses, solved more bluntly:
miniseek *down-weights* documents that cover less of the query, Typesense
*excludes* them. On `sleep quality students` Typesense ranks the one
two-of-three match first, where miniseek's coordination only lifts it to 4th.

**Typo tolerance is the widest gap, and it is not subtle.** `--typo` sends
`diabites prevention`. miniseek silently ignores the unknown term, ranks on
`prevention` alone and returns an *obesity* paper first. Typesense corrects
the spelling and returns the diabetes paper. miniseek does not fail here —
it answers a question nobody asked.

**Stemming differs.** `community transformation` puts a UAV *communications*
paper first in miniseek, because Porter collapses `community` and
`communication` to `commun`. Typesense does not make that mistake.

**Where they agree is the useful reassurance.** `mental health` and
`diabetes prevention` pick the same top document by both engines, which is
evidence miniseek's BM25 and field weighting are implemented correctly rather
than merely plausible.

**Scores are not comparable.** miniseek returns a BM25 float; Typesense
returns a packed `text_match` integer encoding several signals at once.
Compare *orderings*, never the numbers.

## Caveats

The image is pinned to `typesense/typesense:30.2`. Bump it if you want a newer
one — nothing here depends on version-specific behaviour.

The API key is `localdev`, written in the clear in `docker-compose.yml`. It
guards a container bound to `127.0.0.1` and is not a secret; a placeholder that
*looked* like one would invite treating a real key the same way.
