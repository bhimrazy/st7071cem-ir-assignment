import AuthorNames from "./AuthorNames"
import type { PublicationHit } from "../types"

const ABSTRACT_SNIPPET_LENGTH = 280

function snippet(text: string | null): string | null {
  if (!text) return null
  if (text.length <= ABSTRACT_SNIPPET_LENGTH) return text
  return `${text.slice(0, ABSTRACT_SNIPPET_LENGTH).trimEnd()}…`
}

interface ResultItemProps {
  hit: PublicationHit
  /** 1-based position in the ranking, shown so the ordering is explicit. */
  rank: number
  scorer: string
  onSelectAuthor: (name: string) => void
}

/** One Google-Scholar-style result: title link, authors, journal/year, abstract. */
function ResultItem({ hit, rank, scorer, onSelectAuthor }: ResultItemProps) {
  const abstractSnippet = snippet(hit.abstract)

  return (
    <li className="border-b border-line py-5 last:border-b-0">
      <p className="mb-1 flex items-baseline gap-2 text-xs text-faint">
        <span className="font-semibold text-accent">#{rank}</span>
        <span
          className="tabular-nums"
          /* Scores are meaningful only *within* one query: BM25 is unbounded
             and its scale depends on IDF and query length, so this is
             deliberately not shown as a percentage or a confidence. */
          title={`Relevance under ${scorer}. Comparable only within this query.`}
        >
          {scorer} score {hit.score.toFixed(3)}
        </span>
      </p>

      {hit.url ? (
        <a
          href={hit.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-lg leading-snug font-medium text-accent hover:underline"
        >
          {hit.title ?? hit.id}
        </a>
      ) : (
        <span className="text-lg leading-snug font-medium text-ink">
          {hit.title ?? hit.id}
        </span>
      )}

      {hit.authors.length > 0 && (
        <p className="mt-1.5 text-sm text-muted">
          <AuthorNames authors={hit.authors} onSelectAuthor={onSelectAuthor} />
        </p>
      )}

      {(hit.journal || hit.year) && (
        <p className="mt-1 text-sm text-faint italic">
          {hit.journal}
          {hit.journal && hit.year ? " · " : ""}
          {hit.year}
        </p>
      )}

      {abstractSnippet && (
        <p className="mt-2 text-sm leading-relaxed text-muted">{abstractSnippet}</p>
      )}
    </li>
  )
}

export default ResultItem
