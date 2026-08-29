import type { ScorerName } from "../types"

/** The field weights the index is built with, shown so the sum below adds up. */
const FIELD_WEIGHTS: [string, number][] = [
  ["title", 3],
  ["authors", 2],
  ["abstract", 1],
  ["journal", 1],
]

const MAX_SCORE = FIELD_WEIGHTS.reduce((total, [, weight]) => total + weight, 0)

/**
 * What the number beside each result actually is.
 *
 * Worth spelling out because the obvious reading is wrong twice over. A score
 * is not a percentage, and for TF-IDF it is not the cosine either: a document
 * is four fields, so each field contributes its own cosine scaled by that
 * field's weight and the total is their sum. That is why a "cosine" here can
 * read 1.525 when a cosine cannot exceed 1.
 */
export default function ScoreExplainer({ scorer }: { scorer: ScorerName }) {
  const isBm25 = scorer === "bm25"

  return (
    <>
      <p className="mb-2 font-medium text-ink">
        How the {isBm25 ? "BM25" : "TF-IDF"} score is worked out
      </p>

      <p className="mb-2">
        Every query term is scored against each field of the document, and the
        field scores are added up after being weighted:
      </p>

      <p className="mb-2 font-mono text-[11px] text-ink">
        {FIELD_WEIGHTS.map(([field, weight], i) => (
          <span key={field}>
            {i > 0 && " + "}
            {field}&nbsp;&times;&nbsp;{weight}
          </span>
        ))}
      </p>

      <p className="mb-2">
        A match in the title counts three times a match in the abstract, because
        it is stronger evidence the paper is about that word.
      </p>

      <p>
        {isBm25 ? (
          <>
            There is no maximum. BM25 grows with how rare a term is and how
            often it appears, so a score is high or low only relative to the
            other results for the same query.
          </>
        ) : (
          <>
            Each field&rsquo;s share is a cosine and so cannot pass 1, but the
            four are summed after weighting, so the total runs up to{" "}
            {MAX_SCORE}. It is not a percentage and not a plain cosine.
          </>
        )}{" "}
        Scores from different queries, or from the other ranking model, are not
        comparable.
      </p>
    </>
  )
}
