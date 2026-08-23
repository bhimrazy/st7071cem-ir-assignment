/**
 * A small SVG line chart.
 *
 * Hand-drawn rather than pulled from a charting library: three axes, one
 * series and a handful of points does not justify the dependency, and inline
 * SVG inherits the page's colour tokens for free.
 */

interface LineChartProps {
  points: { x: number; y: number }[]
  xLabel: string
  yLabel: string
  colour: string
  /** Drawn as a vertical rule, to mark the value that was chosen. */
  highlightX?: number
  formatY?: (value: number) => string
}

const WIDTH = 320
const HEIGHT = 180
const PADDING = { top: 12, right: 12, bottom: 30, left: 44 }

export default function LineChart({
  points,
  xLabel,
  yLabel,
  colour,
  highlightX,
  formatY = (value) => value.toFixed(2),
}: LineChartProps) {
  if (points.length === 0) return null

  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const xMin = Math.min(...xs)
  const xMax = Math.max(...xs)
  // A flat series would give a zero-height range and divide by zero, so pad it.
  const yMin = Math.min(...ys)
  const yMax = Math.max(...ys)
  const ySpan = yMax - yMin || Math.abs(yMax) || 1

  const plotWidth = WIDTH - PADDING.left - PADDING.right
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom

  const toX = (x: number) =>
    PADDING.left + ((x - xMin) / (xMax - xMin || 1)) * plotWidth
  const toY = (y: number) =>
    PADDING.top + plotHeight - ((y - yMin) / ySpan) * plotHeight

  const path = points.map((p) => `${toX(p.x)},${toY(p.y)}`).join(" ")

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        role="img"
        aria-label={`${yLabel} against ${xLabel}`}
      >
        <line
          x1={PADDING.left}
          y1={PADDING.top}
          x2={PADDING.left}
          y2={PADDING.top + plotHeight}
          stroke="currentColor"
          className="text-line"
        />
        <line
          x1={PADDING.left}
          y1={PADDING.top + plotHeight}
          x2={PADDING.left + plotWidth}
          y2={PADDING.top + plotHeight}
          stroke="currentColor"
          className="text-line"
        />

        {[yMin, yMin + ySpan / 2, yMax].map((value) => (
          <text
            key={value}
            x={PADDING.left - 6}
            y={toY(value) + 3}
            textAnchor="end"
            className="fill-faint text-[8px]"
          >
            {formatY(value)}
          </text>
        ))}

        {points.map((p) => (
          <text
            key={p.x}
            x={toX(p.x)}
            y={HEIGHT - 12}
            textAnchor="middle"
            className="fill-faint text-[8px]"
          >
            {p.x}
          </text>
        ))}

        {highlightX !== undefined && (
          <line
            x1={toX(highlightX)}
            y1={PADDING.top}
            x2={toX(highlightX)}
            y2={PADDING.top + plotHeight}
            stroke={colour}
            strokeDasharray="3 3"
            strokeOpacity={0.5}
          />
        )}

        <polyline
          points={path}
          fill="none"
          stroke={colour}
          strokeWidth={1.5}
          strokeLinejoin="round"
        />

        {points.map((p) => (
          <circle
            key={p.x}
            cx={toX(p.x)}
            cy={toY(p.y)}
            r={p.x === highlightX ? 4 : 2.5}
            fill={colour}
          />
        ))}
      </svg>
      <figcaption className="mt-1 text-center text-xs text-faint">
        {yLabel} vs {xLabel}
      </figcaption>
    </figure>
  )
}
