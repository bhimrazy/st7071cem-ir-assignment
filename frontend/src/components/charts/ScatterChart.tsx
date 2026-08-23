/**
 * The 600 training documents projected to 2D by PCA, coloured by cluster.
 *
 * The projection is computed once on the server at fit time, so this component
 * only has to scale the coordinates into the viewBox.
 */

import type { ProjectedDocument } from "../../types"

interface ScatterChartProps {
  points: ProjectedDocument[]
  colours: Record<string, string>
  /** Marks documents whose cluster disagrees with their true category. */
  showMistakes: boolean
}

const WIDTH = 480
const HEIGHT = 340
const PADDING = 16

export default function ScatterChart({
  points,
  colours,
  showMistakes,
}: ScatterChartProps) {
  if (points.length === 0) return null

  const xs = points.map((p) => p.x)
  const ys = points.map((p) => p.y)
  const xMin = Math.min(...xs)
  const xMax = Math.max(...xs)
  const yMin = Math.min(...ys)
  const yMax = Math.max(...ys)

  const toX = (x: number) =>
    PADDING + ((x - xMin) / (xMax - xMin || 1)) * (WIDTH - PADDING * 2)
  const toY = (y: number) =>
    // SVG y grows downwards, so flip it to read like a normal plot.
    HEIGHT - PADDING - ((y - yMin) / (yMax - yMin || 1)) * (HEIGHT - PADDING * 2)

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="w-full"
      role="img"
      aria-label="Documents projected to two dimensions and coloured by cluster"
    >
      {points.map((point, index) => {
        const misplaced = point.category !== point.true_category
        return (
          <circle
            key={index}
            cx={toX(point.x)}
            cy={toY(point.y)}
            r={showMistakes && misplaced ? 3.5 : 2.4}
            fill={colours[point.category] ?? "#8b909a"}
            fillOpacity={showMistakes && !misplaced ? 0.2 : 0.65}
            stroke={showMistakes && misplaced ? "#101014" : "none"}
            strokeWidth={showMistakes && misplaced ? 1 : 0}
          >
            <title>
              {point.category}
              {misplaced ? ` (actually ${point.true_category})` : ""}
            </title>
          </circle>
        )
      })}
    </svg>
  )
}
