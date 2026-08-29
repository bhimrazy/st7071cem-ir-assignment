import { useId, useState } from "react"

// Opens on focus as well as hover so it is reachable from the keyboard.
export default function InfoTip({ label, children, wide = false }: {
  label: string
  children: React.ReactNode
  /** For explanations that do not fit comfortably in the default width. */
  wide?: boolean
}) {
  const [open, setOpen] = useState(false)
  const id = useId()

  return (
    <span className="relative inline-flex align-middle">
      <button
        type="button"
        aria-label={`What is ${label}?`}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((was) => !was)}
        className="ml-1 flex size-4 cursor-help items-center justify-center rounded-full
          border border-line text-[10px] leading-none font-medium text-faint
          transition hover:border-accent hover:text-accent"
      >
        i
      </button>

      {open && (
        <span
          id={id}
          role="tooltip"
          className={`absolute top-6 right-0 z-20 ${wide ? "w-80" : "w-64"}
            rounded-lg border border-line
            bg-surface p-3 text-left text-xs leading-relaxed font-normal text-muted
            shadow-lg`}
        >
          {children}
        </span>
      )}
    </span>
  )
}
