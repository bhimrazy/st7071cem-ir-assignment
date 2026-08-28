import type { AuthorInfo } from "../types"

interface AuthorNamesProps {
  authors: AuthorInfo[]
  /** Rendered bold and unlinked: the person whose page this already is. */
  highlight?: string
  onSelectAuthor: (name: string) => void
}

/**
 * A publication's author list, comma separated.
 *
 * Only authors with a pureportal profile are clickable. 454 of the 587 author
 * mentions in this corpus are external collaborators who have no Coventry
 * profile, and making every name blue and underlined promised a page that did
 * not exist for three names in four. A plain name is the honest rendering: the
 * person co-wrote the paper, and that is all the crawl knows about them.
 *
 * A button rather than an anchor, because selecting an author navigates inside
 * this engine. An <a> would mislead assistive technology and break middle-click.
 */
function AuthorNames({ authors, highlight, onSelectAuthor }: AuthorNamesProps) {
  return (
    <>
      {authors.map((author, index) => (
        <span key={`${author.name}-${index}`}>
          {author.name === highlight ? (
            <strong className="font-semibold text-ink">{author.name}</strong>
          ) : author.profile_url ? (
            <button
              type="button"
              onClick={() => onSelectAuthor(author.name)}
              title={`Publications by ${author.name} in this index`}
              className="cursor-pointer text-link underline decoration-1 underline-offset-2 hover:text-accent"
            >
              {author.name}
            </button>
          ) : (
            <span title="External co-author, no Coventry profile page">
              {author.name}
            </span>
          )}
          {index < authors.length - 1 ? ", " : ""}
        </span>
      ))}
    </>
  )
}

export default AuthorNames
