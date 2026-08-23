import type { PublicationHit } from "../types"

const ABSTRACT_SNIPPET_LENGTH = 280

function snippet(text: string | null): string | null {
  if (!text) return null
  if (text.length <= ABSTRACT_SNIPPET_LENGTH) return text
  return `${text.slice(0, ABSTRACT_SNIPPET_LENGTH).trimEnd()}…`
}

interface AuthorLinkProps {
  name: string
  onSelectAuthor: (name: string) => void
}

/**
 * An author's name, opening their page inside this engine.
 *
 * A button rather than an anchor: this navigates within the application, and
 * using an <a> would mislead assistive technology and break middle-click.
 * The outward link to pureportal lives on the author page itself.
 */
function AuthorLink({ name, onSelectAuthor }: AuthorLinkProps) {
  return (
    <button
      type="button"
      onClick={() => onSelectAuthor(name)}
      className="cursor-pointer text-link underline decoration-1 underline-offset-2 hover:text-accent"
    >
      {name}
    </button>
  )
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
          {hit.authors.map((name, index) => (
            <span key={`${hit.id}-author-${index}`}>
              <AuthorLink name={name} onSelectAuthor={onSelectAuthor} />
              {index < hit.authors.length - 1 ? ", " : ""}
            </span>
          ))}
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
