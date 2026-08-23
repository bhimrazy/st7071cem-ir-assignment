from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless: nothing here opens a window

import matplotlib.pyplot as plt

from clustering.paths import FIGURES_DIR

CATEGORY_COLOURS = {
    "Economics": "#1f6feb",
    "Entertainment": "#da3633",
    "Politics": "#2ea043",
}


def write_all(report: dict) -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    ks = [point["k"] for point in report["elbow"]]

    _line(
        ks,
        [p["inertia"] for p in report["elbow"]],
        "Inertia (within-cluster sum of squares)",
        "Elbow method for choosing k",
        "#1f6feb",
        "elbow.png",
    )
    _line(
        ks,
        [p["silhouette"] for p in report["elbow"]],
        "Silhouette score",
        "Silhouette score vs k",
        "#da3633",
        "silhouette.png",
    )
    _line(
        ks,
        [p["adjusted_rand_index"] for p in report["elbow"]],
        "Adjusted Rand Index",
        "Agreement with true categories vs k",
        "#7c3aed",
        "ari.png",
    )
    _scatter(report)


def _line(
    ks: list[int],
    values: list[float],
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


def _scatter(report: dict) -> None:
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
