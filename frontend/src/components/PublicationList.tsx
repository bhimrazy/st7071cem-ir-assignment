import type { AuthorPublication } from "../types"

interface PublicationListProps {
  publications: AuthorPublication[]
  onSelectAuthor: (name: string) => void
}

// No score: there is no query here, so ordering is by year rather than rank.
function PublicationList({ publications, onSelectAuthor }: PublicationListProps) {
  return (
    <ul className="m-0 list-none p-0">
      {publications.map((publication) => (
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

          {publication.authors.length > 0 && (
            <p className="mt-1.5 text-sm text-muted">
              {publication.authors.map((name, index) => (
                <span key={`${publication.id}-author-${index}`}>
                  <button
                    type="button"
                    onClick={() => onSelectAuthor(name)}
                    className="cursor-pointer text-link underline decoration-1 underline-offset-2 hover:text-accent"
                  >
                    {name}
                  </button>
                  {index < publication.authors.length - 1 ? ", " : ""}
                </span>
              ))}
            </p>
          )}

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
  )
}

export default PublicationList
