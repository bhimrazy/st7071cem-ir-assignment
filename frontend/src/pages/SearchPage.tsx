import { useCallback, useEffect, useRef, useState } from "react"
import { ApiError, fetchAuthor, fetchPublications, fetchStats, search } from "../api"
import AuthorPanel from "../components/AuthorPanel"
import PublicationList from "../components/PublicationList"
import ResultItem from "../components/ResultItem"
import ScorerToggle from "../components/ScorerToggle"
import SearchBox from "../components/SearchBox"
import type {
  AuthorPublication,
  PublicationHit,
  AuthorResponse,
  ScorerName,
  StatsResponse,
} from "../types"

const PAGE_SIZE = 10

/** Shown on the landing page so the corpus's subject matter is discoverable. */
const EXAMPLE_QUERIES = ["diabetes", "mental health", "midwifery", "wearables"]

interface SearchPageProps {
  /** Current path plus query string, owned by App so the two pages agree. */
  path: string
  navigate: (to: string) => void
}

interface Route {
  query: string
  author: string | null
}

/** Two shapes live under this page: `/?q=...` and `/author/<name>`. */
function readRoute(path: string): Route {
  const [pathname, queryString = ""] = path.split("?")
  const query = new URLSearchParams(queryString).get("q") ?? ""
  const match = pathname.match(/^\/author\/(.+)$/)
  return { query, author: match ? decodeURIComponent(match[1]) : null }
}

function authorPath(name: string, query: string): string {
  const suffix = query ? `?q=${encodeURIComponent(query)}` : ""
  return `/author/${encodeURIComponent(name)}${suffix}`
}

interface ResultsState {
  hits: PublicationHit[]
  total: number
  elapsedMs: number
  /** Taken from the response, not local state, so the label always matches
      the model that actually produced these scores. */
  scorer: string
}

export default function SearchPage({ path, navigate }: SearchPageProps) {
  const [queryInput, setQueryInput] = useState("")
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null)
  const [scorer, setScorer] = useState<ScorerName>("bm25")
  const [results, setResults] = useState<ResultsState | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [author, setAuthor] = useState<AuthorResponse | null>(null)
  const [browse, setBrowse] = useState<AuthorPublication[]>([])
  const [browseTotal, setBrowseTotal] = useState(0)
  const [browseLoading, setBrowseLoading] = useState(false)

  // Guards against a slow, stale request overwriting a faster, later one.
  const requestId = useRef(0)

  const runSearch = useCallback(
    async (
      query: string,
      activeScorer: ScorerName,
      offset: number,
      append: boolean,
    ) => {
      const thisRequest = ++requestId.current
      if (append) setLoadingMore(true)
      else setLoading(true)
      setError(null)

      try {
        const response = await search({
          query,
          limit: PAGE_SIZE,
          offset,
          scorer: activeScorer,
        })
        if (thisRequest !== requestId.current) return

        setResults((previous) => ({
          hits:
            append && previous
              ? [...previous.hits, ...response.hits]
              : response.hits,
          total: response.total,
          elapsedMs: response.elapsed_ms,
          scorer: response.scorer,
        }))
      } catch (err) {
        if (thisRequest !== requestId.current) return
        setError(
          err instanceof ApiError
            ? err.message
            : "Something went wrong. Please try again.",
        )
        if (!append) setResults(null)
      } finally {
        if (thisRequest === requestId.current) {
          setLoading(false)
          setLoadingMore(false)
        }
      }
    },
    [],
  )

  const loadAuthor = useCallback(async (name: string) => {
    try {
      setAuthor(await fetchAuthor(name))
      window.scrollTo({ top: 0, behavior: "smooth" })
    } catch (err) {
      setAuthor(null)
      setError(
        err instanceof ApiError
          ? err.message
          : `Could not load publications for ${name}.`,
      )
    }
  }, [])

  useEffect(() => {
    fetchStats()
      .then(setStats)
      .catch(() => setStats(null))
  }, [])

  // The default listing. Showing the collection before anyone searches is how
  // the source portal behaves, and it makes an empty search box useful rather
  // than a dead end.
  useEffect(() => {
    fetchPublications(PAGE_SIZE, 0)
      .then((response) => {
        setBrowse(response.publications)
        setBrowseTotal(response.total)
      })
      .catch(() => setBrowse([]))
  }, [])

  // The URL is the source of truth. Because App re-renders this page whenever
  // the path changes, a deep link, a link click and the back button all land
  // here and are handled identically.
  useEffect(() => {
    const route = readRoute(path)
    setQueryInput(route.query)
    if (route.query) {
      setSubmittedQuery(route.query)
      void runSearch(route.query, scorer, 0, false)
    } else {
      setSubmittedQuery(null)
      setResults(null)
    }
    if (route.author) void loadAuthor(route.author)
    else setAuthor(null)
    // `scorer` is deliberately excluded: changing it re-runs the search
    // through handleScorerChange without touching the URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, loadAuthor, runSearch])

  const loadMoreBrowse = useCallback(() => {
    setBrowseLoading(true)
    fetchPublications(PAGE_SIZE, browse.length)
      .then((response) =>
        setBrowse((previous) => [...previous, ...response.publications]),
      )
      .catch(() => undefined)
      .finally(() => setBrowseLoading(false))
  }, [browse.length])

  const handleSubmit = (value: string) => {
    // Clearing the box should undo the whole search, not just empty the input.
    navigate(value ? `/?q=${encodeURIComponent(value)}` : "/")
  }

  const handleQueryChange = (value: string) => {
    setQueryInput(value)
    // Covers both the input's native clear control and deleting by hand.
    if (value === "") navigate("/")
  }

  const handleScorerChange = (nextScorer: ScorerName) => {
    setScorer(nextScorer)
    if (submittedQuery !== null) void runSearch(submittedQuery, nextScorer, 0, false)
  }

  const handleLoadMore = () => {
    if (submittedQuery === null || !results) return
    void runSearch(submittedQuery, scorer, results.hits.length, true)
  }

  const openAuthor = (name: string) =>
    navigate(authorPath(name, submittedQuery ?? ""))

  const closeAuthor = () => {
    const query = submittedQuery ?? ""
    navigate(query ? `/?q=${encodeURIComponent(query)}` : "/")
  }

  const hasSearched = submittedQuery !== null
  const hasMore = results !== null && results.hits.length < results.total

  return (
    <div className="flex flex-1 flex-col">
      <div className={hasSearched ? "w-full" : "flex w-full flex-col items-center"}>
        <div
          className={
            hasSearched
              ? "mx-auto flex w-full max-w-3xl flex-col items-center gap-3 border-b border-line px-5 pt-6 pb-4"
              : "flex w-full max-w-3xl flex-col items-center gap-4 px-5 pt-[10vh] pb-10"
          }
        >
          <h1
            className={
              hasSearched
                ? "m-0 text-xl font-semibold tracking-tight text-ink"
                : "m-0 text-center text-4xl font-bold tracking-tight text-ink sm:text-5xl"
            }
          >
            CHCT Publication Search
          </h1>

          {!hasSearched && (
            <p className="m-0 max-w-md text-center text-pretty text-muted">
              Search publications from Coventry University&rsquo;s Centre for
              Healthcare and Community Transformation.
            </p>
          )}

          <SearchBox
            value={queryInput}
            onChange={handleQueryChange}
            onSubmit={handleSubmit}
            compact={hasSearched}
          />

          {!hasSearched && (
            <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
              <span className="text-sm text-faint">Try</span>
              {EXAMPLE_QUERIES.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => handleSubmit(example)}
                  className="cursor-pointer rounded-full border border-line px-3 py-1 text-sm
                    text-muted transition hover:border-accent hover:text-accent"
                >
                  {example}
                </button>
              ))}
            </div>
          )}

          {hasSearched && (
            <div className="flex w-full justify-end">
              <ScorerToggle value={scorer} onChange={handleScorerChange} />
            </div>
          )}
        </div>
      </div>

      {!hasSearched && !author && (
        <section className="mx-auto w-full max-w-3xl px-5 pb-16">
          <div className="flex items-baseline justify-between border-b border-line pb-2">
            <h2 className="m-0 text-base font-semibold text-ink">
              Recent publications
            </h2>
            <span className="text-sm text-faint">
              {browseTotal.toLocaleString()} in this index
            </span>
          </div>

          <PublicationList publications={browse} onSelectAuthor={openAuthor} />

          {browse.length < browseTotal && (
            <button
              type="button"
              onClick={loadMoreBrowse}
              disabled={browseLoading}
              className="mx-auto mt-8 block cursor-pointer rounded-full border border-line px-6 py-2
                text-sm text-muted transition hover:border-accent hover:text-accent
                disabled:cursor-default disabled:opacity-50"
            >
              {browseLoading ? "Loading…" : "Load more"}
            </button>
          )}

          {stats && (
            <footer className="pt-10 text-center text-xs text-faint">
              {stats.document_count.toLocaleString()} publications indexed &middot;{" "}
              {stats.vocabulary_size.toLocaleString()} terms
              {stats.last_crawled_at
                ? ` · last crawled ${stats.last_crawled_at.slice(0, 10)}`
                : ""}
            </footer>
          )}
        </section>
      )}

      {author && (
        <AuthorPanel
          author={author}
          onClose={closeAuthor}
          onSelectAuthor={openAuthor}
        />
      )}

      {!author && hasSearched && (
        <section
          className="mx-auto w-full max-w-3xl flex-1 px-5 pb-16"
          aria-live="polite"
        >
          {loading && <p className="py-10 text-center text-muted">Searching…</p>}

          {!loading && error && (
            <p className="py-10 text-center text-red-600" role="alert">
              {error}
            </p>
          )}

          {!loading && !error && results && results.total === 0 && (
            <p className="py-10 text-center text-muted">
              No results for{" "}
              <strong className="text-ink">&ldquo;{submittedQuery}&rdquo;</strong>.
            </p>
          )}

          {!loading && !error && results && results.total > 0 && (
            <>
              <p className="py-4 text-sm text-faint">
                About {results.total.toLocaleString()} result
                {results.total === 1 ? "" : "s"} (
                {(results.elapsedMs / 1000).toFixed(3)} seconds)
              </p>
              <ul className="m-0 list-none p-0">
                {results.hits.map((hit, index) => (
                  <ResultItem
                    key={hit.id}
                    hit={hit}
                    rank={index + 1}
                    scorer={results.scorer}
                    onSelectAuthor={openAuthor}
                  />
                ))}
              </ul>
              {hasMore && (
                <button
                  type="button"
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  className="mx-auto mt-8 block cursor-pointer rounded-full border border-line px-6 py-2
                    text-sm text-muted transition hover:border-accent hover:text-accent
                    disabled:cursor-default disabled:opacity-50"
                >
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
              )}
            </>
          )}
        </section>
      )}
    </div>
  )
}
