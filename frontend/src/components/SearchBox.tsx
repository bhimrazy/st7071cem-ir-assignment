import type { FormEvent } from "react"

interface SearchBoxProps {
  value: string
  onChange: (value: string) => void
  onSubmit: (value: string) => void
  compact?: boolean
}

/** The search input, shared by the landing state and the results header. */
function SearchBox({ value, onChange, onSubmit, compact = false }: SearchBoxProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    onSubmit(value.trim())
  }

  return (
    <form
      className={`group flex w-full items-center gap-3 rounded-full border border-line bg-surface shadow-sm transition
        focus-within:border-accent focus-within:shadow-[0_0_0_4px_var(--color-accent-soft)] hover:shadow-md
        ${compact ? "max-w-full py-2 pr-2 pl-4" : "max-w-2xl py-3 pr-3 pl-5"}`}
      role="search"
      onSubmit={handleSubmit}
    >
      <label htmlFor="search-input" className="sr-only">
        Search CHCT publications
      </label>
      <svg
        className="size-5 shrink-0 text-faint"
        viewBox="0 0 24 24"
        aria-hidden="true"
        focusable="false"
      >
        <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" stroke="currentColor" strokeWidth="2" />
      </svg>
      <input
        id="search-input"
        type="search"
        name="q"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Search titles, authors, abstracts…"
        autoComplete="off"
        autoFocus={!compact}
        className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-faint
          [&::-webkit-search-cancel-button]:cursor-pointer"
      />
      <button
        type="submit"
        className={`shrink-0 rounded-full bg-accent font-medium text-white transition hover:brightness-110
          focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent
          ${compact ? "px-4 py-1.5 text-sm" : "px-6 py-2.5"}`}
      >
        Search
      </button>
    </form>
  )
}

export default SearchBox
