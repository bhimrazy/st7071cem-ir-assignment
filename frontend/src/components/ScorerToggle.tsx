import type { ScorerName } from "../types"

interface ScorerToggleProps {
  value: ScorerName
  onChange: (value: ScorerName) => void
}

const OPTIONS: { id: ScorerName; label: string }[] = [
  { id: "bm25", label: "BM25" },
  { id: "tf-idf", label: "TF-IDF" },
]

function ScorerToggle({ value, onChange }: ScorerToggleProps) {
  return (
    <div
      className="inline-flex items-center gap-1 rounded-full border border-line bg-surface-soft p-1"
      role="group"
      aria-label="Ranking model"
    >
      {OPTIONS.map((option) => {
        const active = option.id === value
        return (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange(option.id)}
            aria-pressed={active}
            className={`rounded-full px-3.5 py-1 text-sm transition ${
              active
                ? "bg-surface font-medium text-accent shadow-sm"
                : "text-muted hover:text-ink"
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export default ScorerToggle
