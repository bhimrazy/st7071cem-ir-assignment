/** Top bar switching between the two coursework tasks. */

export type TaskView = "search" | "clustering"

interface NavHeaderProps {
  active: TaskView
  onNavigate: (view: TaskView) => void
}

const TABS: { view: TaskView; label: string; hint: string }[] = [
  { view: "search", label: "Search engine", hint: "Task 1" },
  { view: "clustering", label: "Document clustering", hint: "Task 2" },
]

export default function NavHeader({ active, onNavigate }: NavHeaderProps) {
  return (
    <header className="sticky top-0 z-10 border-b border-line bg-surface/90 backdrop-blur">
      <nav className="mx-auto flex w-full max-w-5xl items-center gap-1 px-5 py-2">
        <span className="mr-3 text-sm font-semibold tracking-tight text-ink">
          ST7071CEM
        </span>
        {TABS.map((tab) => {
          const isActive = tab.view === active
          return (
            <button
              key={tab.view}
              type="button"
              onClick={() => onNavigate(tab.view)}
              aria-current={isActive ? "page" : undefined}
              className={`cursor-pointer rounded-full px-3 py-1.5 text-sm transition ${
                isActive
                  ? "bg-accent-soft font-medium text-accent"
                  : "text-muted hover:text-ink"
              }`}
            >
              {tab.label}
              <span className="ml-1.5 text-xs text-faint">{tab.hint}</span>
            </button>
          )
        })}
      </nav>
    </header>
  )
}
