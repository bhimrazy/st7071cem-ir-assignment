import { useCallback, useEffect, useState } from "react"
import { classifyDocument, fetchClusteringOverview } from "../api"
import InfoTip from "../components/InfoTip"
import LineChart from "../components/charts/LineChart"
import ScatterChart from "../components/charts/ScatterChart"
import type { ClassifyResponse, ClusteringOverview } from "../types"

const CATEGORY_COLOURS: Record<string, string> = {
  Economics: "#1f6feb",
  Entertainment: "#da3633",
  Politics: "#2ea043",
}

const METRICS: Record<string, { label: string; help: string }> = {
  adjusted_rand_index: {
    label: "Adjusted Rand Index",
    help: "Takes every pair of documents and asks whether the clustering agrees with the true categories about keeping them together or apart. 1 is perfect agreement, 0 is what random guessing would score.",
  },
  normalized_mutual_info: {
    label: "Normalised Mutual Information",
    help: "How much knowing a document's cluster tells you about its true category, on a 0 to 1 scale. Unlike accuracy it does not need the clusters to be named.",
  },
  homogeneity: {
    label: "Homogeneity",
    help: "Whether each cluster contains only one category. Splitting Politics across two clean clusters still scores 1 here.",
  },
  completeness: {
    label: "Completeness",
    help: "Whether each category ends up in a single cluster. The mirror image of homogeneity: putting everything in one big cluster scores 1 here.",
  },
  v_measure: {
    label: "V-measure",
    help: "Homogeneity and completeness combined into one number, so neither can be gamed on its own.",
  },
  accuracy: {
    label: "Agreement with true labels",
    help: "The share of documents whose cluster carries the same name as their true category. Readable, but it depends on the majority-vote naming step, which the other scores do not.",
  },
}

export default function ClusteringPage() {
  const [overview, setOverview] = useState<ClusteringOverview | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [text, setText] = useState("")
  const [result, setResult] = useState<ClassifyResponse | null>(null)
  const [classifying, setClassifying] = useState(false)
  const [classifyError, setClassifyError] = useState<string | null>(null)
  const [showMistakes, setShowMistakes] = useState(false)

  useEffect(() => {
    fetchClusteringOverview()
      .then(setOverview)
      .catch(() =>
        setLoadError(
          "Could not load the clustering model. Run scripts/run_clustering.py to build it.",
        ),
      )
  }, [])

  const submit = useCallback(async (value: string) => {
    const trimmed = value.trim()
    if (!trimmed) return
    setClassifying(true)
    setClassifyError(null)
    try {
      setResult(await classifyDocument(trimmed))
    } catch {
      setClassifyError("Could not classify that document. Please try again.")
      setResult(null)
    } finally {
      setClassifying(false)
    }
  }, [])

  const useExample = (example: string) => {
    setText(example)
    void submit(example)
  }

  if (loadError) {
    return (
      <main className="mx-auto w-full max-w-3xl px-5 py-16">
        <p className="text-center text-red-600">{loadError}</p>
      </main>
    )
  }

  if (!overview) {
    return (
      <main className="mx-auto w-full max-w-3xl px-5 py-16">
        <p className="text-center text-muted">Loading the clustering model…</p>
      </main>
    )
  }

  const { corpus, clusters, metrics, confusion, elbow } = overview

  return (
    <main className="mx-auto w-full max-w-5xl px-5 pb-20">
      <section className="pt-8 pb-6">
        <h1 className="m-0 text-2xl font-bold tracking-tight text-ink">
          Document clustering
        </h1>
        <p className="mt-2 max-w-2xl text-pretty text-muted">
          {corpus.total.toLocaleString()} BBC News articles grouped into{" "}
          {overview.k} clusters by k-means over TF-IDF vectors. The model is
          never shown the true categories while clustering; they are used
          afterwards only to give each cluster a name and to measure how well it
          did.
        </p>
      </section>

      {/* --- Assign a new document: the brief's final requirement. --- */}
      <section className="rounded-xl border border-line bg-surface-soft p-5">
        <h2 className="m-0 text-base font-semibold text-ink">
          Assign a new document
        </h2>
        <p className="mt-1 text-sm text-muted">
          Paste a sentence or a paragraph. The model has never seen it before.
        </p>

        <form
          onSubmit={(event) => {
            event.preventDefault()
            void submit(text)
          }}
          className="mt-3"
        >
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={4}
            placeholder="The central bank raised interest rates again this morning…"
            className="w-full resize-y rounded-lg border border-line bg-surface px-3 py-2
              text-ink outline-none placeholder:text-faint focus:border-accent"
          />
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button
              type="submit"
              disabled={classifying || !text.trim()}
              className="cursor-pointer rounded-full bg-accent px-5 py-2 text-sm font-medium
                text-white transition hover:opacity-90 disabled:cursor-default disabled:opacity-40"
            >
              {classifying ? "Assigning…" : "Assign to a cluster"}
            </button>
            {(text || result) && (
              <button
                type="button"
                onClick={() => {
                  setText("")
                  setResult(null)
                  setClassifyError(null)
                }}
                className="cursor-pointer rounded-full border border-line px-4 py-2 text-sm
                  text-muted transition hover:border-accent hover:text-accent"
              >
                Clear
              </button>
            )}
          </div>
        </form>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-sm text-faint">Or try</span>
          {overview.examples.map((example, index) => (
            <button
              key={index}
              type="button"
              onClick={() => useExample(example)}
              title={example}
              className="cursor-pointer rounded-full border border-line px-3 py-1 text-sm
                text-muted transition hover:border-accent hover:text-accent"
            >
              {example.split(" ").slice(0, 4).join(" ")}…
            </button>
          ))}
        </div>

        {classifyError && (
          <p className="mt-4 text-sm text-red-600" role="alert">
            {classifyError}
          </p>
        )}

        {result && !classifyError && (
          <div
            className="mt-4 rounded-lg border-l-4 bg-surface p-4"
            style={{ borderLeftColor: CATEGORY_COLOURS[result.category] }}
            aria-live="polite"
          >
            <p className="m-0 text-ink">
              This document has been assigned to the{" "}
              <strong style={{ color: CATEGORY_COLOURS[result.category] }}>
                {result.category}
              </strong>{" "}
              cluster{" "}
              <span className="text-faint">(cluster {result.cluster_id})</span>.
            </p>

            <p className="mt-3 mb-1 text-xs font-medium text-muted">
              Distance from your text to each cluster centre, nearest wins
            </p>
            <dl className="m-0">
              {Object.entries(result.distances)
                .sort((a, b) => a[1] - b[1])
                .map(([category, distance], index) => {
                  const isWinner = category === result.category
                  const gap = distance - nearest(result.distances)
                  return (
                    <div key={category} className="flex items-center gap-3 py-1">
                      <dt
                        className={`w-28 shrink-0 text-sm ${
                          isWinner ? "font-medium text-ink" : "text-muted"
                        }`}
                      >
                        {category}
                      </dt>
                      <dd className="m-0 flex flex-1 items-center gap-3">
                        {/* Every distance sits near 1 in a sparse
                            high-dimension space, so a bar drawn from zero would
                            make all three look identical. It is scaled to the
                            spread instead, and the raw number is printed too. */}
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-soft">
                          <div
                            className="h-full rounded-full"
                            style={{
                              width: `${barWidth(distance, result.distances)}%`,
                              background: isWinner
                                ? CATEGORY_COLOURS[category]
                                : "#c9ccd3",
                            }}
                          />
                        </div>
                        <span className="w-14 text-right text-xs tabular-nums text-faint">
                          {distance.toFixed(4)}
                        </span>
                        <span className="w-24 text-right text-xs tabular-nums text-faint">
                          {index === 0 ? "nearest" : `+${gap.toFixed(4)} further`}
                        </span>
                      </dd>
                    </div>
                  )
                })}
            </dl>

            <p className="mt-3 text-xs leading-relaxed text-faint">
              These are straight-line distances in the 5,000-dimension TF-IDF
              space, not probabilities, and they do not add up to 1. Almost any
              document sits close to distance 1 from every centre in a space
              that large, so the numbers look alike by nature. What decides the
              answer is the ordering, and here the gap to the runner-up is{" "}
              {(result.margin * 100).toFixed(1)}% of its distance.
            </p>
            <p className="mt-1 text-xs leading-relaxed text-faint">
              {result.matched_term_count > 0 ? (
                <>
                  Your text matched {result.matched_term_count} term
                  {result.matched_term_count === 1 ? "" : "s"} the model knows
                  {result.matched_terms.length > 0 && (
                    <>
                      , the heaviest being{" "}
                      <span className="text-muted">
                        {result.matched_terms.join(", ")}
                      </span>
                    </>
                  )}
                  . Anything outside the training vocabulary is ignored.
                </>
              ) : (
                "None of these words appear in the training vocabulary, so there was nothing to measure and this assignment is arbitrary."
              )}
            </p>
          </div>
        )}
      </section>

      {/* --- What the clusters are made of --- */}
      <section className="pt-10">
        <h2 className="m-0 flex items-center text-base font-semibold text-ink">
          The clusters
          <InfoTip label="the clusters">
            K-means put every article in one of three groups without being told
            the categories. Each card lists the words that group uses far more
            than the other two, which is how you tell what it is about.
          </InfoTip>
        </h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-3">
          {clusters.map((cluster) => (
            <article
              key={cluster.cluster_id}
              className="rounded-xl border border-line p-4"
              style={{ borderTopColor: CATEGORY_COLOURS[cluster.category], borderTopWidth: 3 }}
            >
              <h3
                className="m-0 text-sm font-semibold"
                style={{ color: CATEGORY_COLOURS[cluster.category] }}
              >
                {cluster.category}
              </h3>
              <p className="mt-0.5 text-xs text-faint">
                cluster {cluster.cluster_id} · {cluster.size} documents ·{" "}
                {corpus.counts[cluster.category]} truly in this category
              </p>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                {cluster.top_terms.join(", ")}
              </p>
            </article>
          ))}
        </div>
        <p className="mt-2 max-w-3xl text-xs text-faint">
          Words are shown stemmed, so &ldquo;elect&rdquo; covers election and
          elected. These are the terms each cluster weights most heavily
          <em> compared with the other two</em>, rather than its heaviest terms
          outright: &ldquo;said&rdquo; is in 87% of BBC articles and tops all
          three centres, so it describes none of them. The category names were
          attached afterwards by majority vote.
        </p>
      </section>

      {/* --- Charts --- */}
      <section className="pt-10">
        <h2 className="m-0 flex items-center text-base font-semibold text-ink">
          Choosing k
          <InfoTip label="choosing k">
            k is how many clusters k-means is told to find. It cannot work this
            out itself, so these three curves are the evidence for picking 3.
          </InfoTip>
        </h2>
        <div className="mt-3 grid gap-6 sm:grid-cols-3">
          <LineChart
            points={elbow.map((p) => ({ x: p.k, y: p.inertia }))}
            xLabel="k"
            yLabel="Inertia"
            colour="#1f6feb"
            highlightX={overview.k}
            formatY={(value) => value.toFixed(0)}
          />
          <LineChart
            points={elbow.map((p) => ({ x: p.k, y: p.silhouette }))}
            xLabel="k"
            yLabel="Silhouette"
            colour="#da3633"
            highlightX={overview.k}
            formatY={(value) => value.toFixed(3)}
          />
          <LineChart
            points={elbow.map((p) => ({
              x: p.k,
              y: p.adjusted_rand_index ?? 0,
            }))}
            xLabel="k"
            yLabel="Adjusted Rand Index"
            colour="#7c3aed"
            highlightX={overview.k}
            formatY={(value) => value.toFixed(2)}
          />
        </div>
        <p className="mt-2 max-w-3xl text-xs text-faint">
          Inertia always falls as k grows, so it can only suggest an elbow.
          Silhouette barely moves here, which is normal for sparse text where
          almost every pair of documents is nearly orthogonal. The Adjusted Rand
          Index peaks sharply at k={overview.k}, but it can only be computed
          because this corpus happens to carry true labels.
        </p>
      </section>

      <section className="pt-10">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="m-0 flex items-center text-base font-semibold text-ink">
            Documents in two dimensions
            <InfoTip label="this chart">
              Every article is a point in 5,000 dimensions, one per vocabulary
              term, which cannot be drawn. PCA flattens that to the two
              directions carrying the most variation so it fits on a page. Each
              point is one article, coloured by the cluster it was put in.
            </InfoTip>
          </h2>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
            <input
              type="checkbox"
              checked={showMistakes}
              onChange={(event) => setShowMistakes(event.target.checked)}
              className="accent-accent"
            />
            Highlight misplaced documents
          </label>
        </div>
        <div className="mt-3 grid gap-6 sm:grid-cols-[1fr_auto] sm:items-center">
          <ScatterChart
            points={overview.projection}
            colours={CATEGORY_COLOURS}
            showMistakes={showMistakes}
          />
          <ul className="m-0 list-none space-y-2 p-0">
            {clusters.map((cluster) => (
              <li
                key={cluster.cluster_id}
                className="flex items-center gap-2 text-sm text-muted"
              >
                <span
                  className="inline-block size-3 rounded-full"
                  style={{ background: CATEGORY_COLOURS[cluster.category] }}
                />
                {cluster.category}
              </li>
            ))}
          </ul>
        </div>
        <p className="mt-2 text-xs text-faint">
          The 5,000-dimension TF-IDF vectors projected to two dimensions by PCA.
          Most of the original separation is lost in the projection, so
          overlapping points here are a limit of the picture, not necessarily a
          clustering error.
        </p>
      </section>

      {/* --- Evaluation --- */}
      <section className="pt-10">
        <h2 className="m-0 flex items-center text-base font-semibold text-ink">
          How well it did
          <InfoTip label="these scores">
            The clustering ran blind, but we do know each article&rsquo;s real
            category, so we can check the result against it afterwards. Every
            score below is 0 to 1, higher is better.
          </InfoTip>
        </h2>
        <div className="mt-3 grid gap-6 sm:grid-cols-2">
          <dl className="m-0 divide-y divide-line">
            {Object.entries(metrics).map(([key, value]) => (
              <div key={key} className="flex items-baseline justify-between py-2">
                <dt className="flex items-center text-sm text-muted">
                  {METRICS[key]?.label ?? key}
                  {METRICS[key] && (
                    <InfoTip label={METRICS[key].label}>
                      {METRICS[key].help}
                    </InfoTip>
                  )}
                </dt>
                <dd className="m-0 text-sm font-medium tabular-nums text-ink">
                  {key === "accuracy"
                    ? `${(value * 100).toFixed(1)}%`
                    : value.toFixed(3)}
                </dd>
              </div>
            ))}
          </dl>

          <div>
            <p className="mb-2 flex items-center text-sm font-medium text-ink">
              Where every article ended up
              <InfoTip label="this table">
                Read a row as &ldquo;of the 200 real Economics articles, this
                many went to each cluster&rdquo;. The diagonal is the ones that
                went where they should. Anything off the diagonal is a mistake,
                and its position tells you which two categories the model
                confused.
              </InfoTip>
            </p>
            <div className="overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <caption className="pb-2 text-left text-xs text-faint">
                Rows are the true category. Columns are the cluster the article
                was put in. Bold is correct.
              </caption>
              <thead>
                <tr>
                  <th className="p-2" />
                  {confusion.cols.map((col) => (
                    <th
                      key={col}
                      className="p-2 text-right text-xs font-medium text-muted"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {confusion.rows.map((row, rowIndex) => (
                  <tr key={row} className="border-t border-line">
                    <th className="p-2 text-left text-xs font-medium text-muted">
                      {row}
                    </th>
                    {confusion.matrix[rowIndex].map((value, colIndex) => (
                      <td
                        key={colIndex}
                        className={`p-2 text-right tabular-nums ${
                          confusion.cols[colIndex] === row
                            ? "font-semibold text-ink"
                            : "text-faint"
                        }`}
                      >
                        {value}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-faint">
              {mistakeSummary(confusion)}
            </p>
          </div>
        </div>
      </section>

      <footer className="mt-12 border-t border-line pt-6 text-xs leading-relaxed text-faint">
        <p className="m-0">
          Corpus: {corpus.total.toLocaleString()} articles (
          {corpus.categories
            .map((c) => `${corpus.counts[c]} ${c.toLowerCase()}`)
            .join(", ")}
          ), {overview.vocabulary_size.toLocaleString()} term vocabulary.
        </p>
        <p className="m-0 mt-1">
          The archive labels these folders business, entertainment and politics,
          and its sport and tech folders are not used here. Economics is the
          business folder relabelled. That folder is a mix: some articles are
          macroeconomic reporting (growth, unemployment, oil prices) and some
          are company news (takeovers, results, deals). It is the closest of
          the five folders to the brief&rsquo;s Economics, not an exact match.
        </p>
        <p className="m-0 mt-1">{corpus.citation}</p>
        <p className="m-0 mt-1">
          {corpus.licence_note}{" "}
          <a
            href={corpus.original_source}
            target="_blank"
            rel="noreferrer"
            className="text-link underline decoration-1 underline-offset-2"
          >
            Dataset home page
          </a>
        </p>
      </footer>
    </main>
  )
}

/**
 * Scale a distance across the visible range of the three distances.
 *
 * Every distance sits near 1, so a bar drawn from zero would make all three
 * look identical. Scaling to the spread makes the ordering readable, at the
 * cost of the bar no longer being proportional to the raw value, which is why
 * the number is printed next to it.
 */
/** A plain-English reading of the off-diagonal cells, counts only. */
function mistakeSummary(confusion: ClusteringOverview["confusion"]): string {
  const mistakes: string[] = []
  let wrong = 0
  confusion.rows.forEach((row, r) =>
    confusion.cols.forEach((col, c) => {
      const count = confusion.matrix[r][c]
      if (row !== col && count > 0) {
        wrong += count
        mistakes.push(`${count} ${row} into ${col}`)
      }
    }),
  )
  const total = confusion.matrix.flat().reduce((a, b) => a + b, 0)
  if (wrong === 0) return "Every article landed in the right cluster."
  return `${wrong} of ${total} articles went to the wrong cluster: ${mistakes.join(", ")}.`
}

function nearest(all: Record<string, number>): number {
  return Math.min(...Object.values(all))
}

function barWidth(distance: number, all: Record<string, number>): number {
  const values = Object.values(all)
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (max === min) return 100
  return 25 + ((max - distance) / (max - min)) * 75
}
