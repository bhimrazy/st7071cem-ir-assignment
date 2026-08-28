import AuthorNames from "./AuthorNames"
import type { AuthorResponse } from "../types"

interface AuthorPanelProps {
  author: AuthorResponse
  onClose: () => void
  onSelectAuthor: (name: string) => void
}

/**
 * An author's page, assembled from our own index.
 *
 * Selecting an author stays inside this engine rather than navigating straight
 * out to pureportal. That is the point of a vertical search engine: we hold
 * the department's output, so we can answer "what else did they publish?"
 * directly. The outward link to the original profile, which the coursework
 * brief requires, is offered prominently here.
 */
function AuthorPanel({ author, onClose, onSelectAuthor }: AuthorPanelProps) {
  const span =
    author.first_year && author.last_year
      ? author.first_year === author.last_year
        ? author.first_year
        : `${author.first_year}–${author.last_year}`
      : null

  return (
    <section
      className="mx-auto w-full max-w-3xl px-5 pb-16"
      aria-label={`Publications by ${author.name}`}
    >
      <button
        type="button"
        onClick={onClose}
        className="mb-5 cursor-pointer text-sm text-accent hover:underline"
      >
        &larr; Back to results
      </button>

      <header className="border-b border-line pb-5">
        <h2 className="m-0 text-3xl font-semibold text-ink">{author.name}</h2>
        <p className="mt-2 text-sm text-muted">
          {author.publication_count} publication
          {author.publication_count === 1 ? "" : "s"} in this index
          {span ? ` · ${span}` : ""}
          {author.co_author_count > 0 ? ` · ${author.co_author_count} co-authors` : ""}
        </p>
        {author.profile_url ? (
          <a
            href={author.profile_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-4 py-1.5
              text-sm font-medium text-accent transition hover:brightness-95"
          >
            View full profile on pureportal
            <span aria-hidden="true">&rarr;</span>
          </a>
        ) : (
          <p className="mt-3 text-sm text-faint italic">
            External co-author &mdash; no Coventry profile page
          </p>
        )}
      </header>

      <ul className="m-0 list-none p-0">
        {author.publications.map((publication) => (
          <li key={publication.id} className="border-b border-line py-5 last:border-b-0">
            {publication.url ? (
              <a
                href={publication.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-lg leading-snug font-medium text-accent hover:underline"
              >
                {publication.title ?? publication.id}
              </a>
            ) : (
              <span className="text-lg leading-snug font-medium text-ink">
                {publication.title ?? publication.id}
              </span>
            )}

            <p className="mt-1.5 text-sm text-muted">
              <AuthorNames
                authors={publication.authors}
                highlight={author.name}
                onSelectAuthor={onSelectAuthor}
              />
            </p>

            {(publication.journal || publication.year) && (
              <p className="mt-1 text-sm text-faint italic">
                {publication.journal}
                {publication.journal && publication.year ? " · " : ""}
                {publication.year}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default AuthorPanel
