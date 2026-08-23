"""Task 2 end to end: load the corpus, fit, evaluate, save artefacts, demo.

uv run python scripts/run_clustering.py
uv run python scripts/run_clustering.py --per-category 100
uv run python scripts/run_clustering.py --all          # no sampling
"""

from __future__ import annotations

import argparse

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from clustering.dataset import DOCUMENTS_PER_CATEGORY, load_corpus
from clustering.paths import FIGURES_DIR, MODEL_PATH, REPORT_PATH
from clustering.pipeline import EXAMPLE_DOCUMENTS, build

CATEGORY_COLOURS = {
    "Economics": "#1f6feb",
    "Entertainment": "#da3633",
    "Politics": "#2ea043",
}


def main() -> None:
    args = _parse_args()
    per_category = None if args.all else args.per_category

    corpus = load_corpus(per_category=per_category)
    _section("1. Corpus")
    print(f"Documents:   {len(corpus)}")
    print(f"Categories:  {dict(corpus.provenance.category_counts)}")
    print(f"Source:      {corpus.provenance.source}")
    print(f"Citation:    {corpus.provenance.citation}")

    _section("2. Fitting TF-IDF + K-means")
    artifacts = build(corpus=corpus)
    model, report = artifacts.model, artifacts.report
    print(f"Vocabulary:  {report['vocabulary_size']} terms")
    print(f"k:           {report['k']}")
    print(f"Mapping:     {model.cluster_to_category}")

    _section("3. Top terms per cluster")
    for cluster in report["clusters"]:
        print(
            f"  cluster {cluster['cluster_id']} -> {cluster['category']} "
            f"(n={cluster['size']})"
        )
        print(f"    {', '.join(cluster['top_terms'])}")

    _section("4. Choosing k")
    for point in report["elbow"]:
        marker = "  <- chosen" if point["k"] == report["k"] else ""
        print(
            f"  k={point['k']}  inertia={point['inertia']:>9.2f}  "
            f"silhouette={point['silhouette']:+.4f}  "
            f"ARI={point['adjusted_rand_index']:.4f}{marker}"
        )

    _section("5. Evaluation")
    for name, value in report["metrics"].items():
        print(f"  {name.replace('_', ' '):<26} {value:.4f}")

    print("\nConfusion matrix (rows = true, columns = assigned):")
    confusion = report["confusion"]
    print(" " * 16 + "".join(f"{c:>16}" for c in confusion["cols"]))
    for label, row in zip(confusion["rows"], confusion["matrix"], strict=True):
        print(f"{label:<16}" + "".join(f"{v:>16}" for v in row))

    _section("6. Artefacts")
    print(f"Model:   {MODEL_PATH}")
    print(f"Report:  {REPORT_PATH}")
    _write_figures(report)
    print(f"Figures: {FIGURES_DIR}")

    _section("7. Assigning new, unseen documents")
    for text in EXAMPLE_DOCUMENTS:
        assignment = model.predict(text)
        print(f'\n  "{text[:72]}..."')
        print(
            f"    -> {assignment.category} (cluster {assignment.cluster_id}), "
            f"margin {assignment.margin:.3f}"
        )
        print(f"    matched terms: {', '.join(assignment.matched_terms)}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-category", type=int, default=DOCUMENTS_PER_CATEGORY)
    parser.add_argument("--all", action="store_true", help="use every article")
    return parser.parse_args()


def _section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def _write_figures(report: dict) -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    ks = [p["k"] for p in report["elbow"]]

    _line_plot(
        ks,
        [p["inertia"] for p in report["elbow"]],
        ylabel="Inertia (within-cluster sum of squares)",
        title="Elbow method for choosing k",
        colour="#1f6feb",
        filename="elbow.png",
    )
    _line_plot(
        ks,
        [p["silhouette"] for p in report["elbow"]],
        ylabel="Silhouette score",
        title="Silhouette score vs k",
        colour="#da3633",
        filename="silhouette.png",
    )
    _line_plot(
        ks,
        [p["adjusted_rand_index"] for p in report["elbow"]],
        ylabel="Adjusted Rand Index",
        title="Agreement with true categories vs k",
        colour="#7c3aed",
        filename="ari.png",
    )
    _scatter_plot(report)


def _line_plot(
    ks: list[int],
    values: list[float],
    *,
    ylabel: str,
    title: str,
    colour: str,
    filename: str,
) -> None:
    fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
    ax.plot(ks, values, marker="o", color=colour)
    ax.set_xlabel("Number of clusters (k)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(ks)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / filename)
    plt.close(fig)


def _scatter_plot(report: dict) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 5), dpi=150)
    for cluster in report["clusters"]:
        points = [
            p for p in report["projection"] if p["cluster_id"] == cluster["cluster_id"]
        ]
        ax.scatter(
            [p["x"] for p in points],
            [p["y"] for p in points],
            s=14,
            alpha=0.6,
            color=CATEGORY_COLOURS.get(cluster["category"]),
            label=f"{cluster['category']} (cluster {cluster['cluster_id']})",
        )
    ax.set_xlabel("PCA component 1")
    ax.set_ylabel("PCA component 2")
    ax.set_title("K-means clusters projected to 2D (PCA)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "pca_scatter.png")
    plt.close(fig)


if __name__ == "__main__":
    main()
