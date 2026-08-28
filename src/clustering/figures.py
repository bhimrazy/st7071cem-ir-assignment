from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless: nothing here opens a window

import matplotlib.pyplot as plt

from clustering.paths import FIGURES_DIR
from clustering.pipeline import Report

# Greyscale, because the report prints in black and white. Clusters are told
# apart by marker shape as well as fill, so the scatter survives being printed
# and stays readable to anyone who cannot distinguish the shades.
INK = "#111111"
CATEGORY_STYLES = {
    "Economics": ("o", "#111111"),
    "Entertainment": ("s", "#888888"),
    "Politics": ("^", "#ffffff"),
}


def write_all(report: Report) -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    ks = [point["k"] for point in report["elbow"]]

    _line(
        ks,
        [p["inertia"] for p in report["elbow"]],
        "Inertia (within-cluster sum of squares)",
        "Elbow method for choosing k",
        "elbow.png",
    )
    _line(
        ks,
        [p["silhouette"] for p in report["elbow"]],
        "Silhouette score",
        "Silhouette score vs k",
        "silhouette.png",
    )
    # ARI is only recorded when the sweep was given the true labels.
    ari = [point["adjusted_rand_index"] for point in report["elbow"]]
    if None not in ari:
        _line(
            ks,
            [float(value) for value in ari if value is not None],
            "Adjusted Rand Index",
            "Agreement with true categories vs k",
            "ari.png",
        )
    _scatter(report)


def _line(
    ks: list[int],
    values: list[float],
    ylabel: str,
    title: str,
    filename: str,
) -> None:
    fig, ax = plt.subplots(figsize=(6, 4), dpi=150)
    ax.plot(ks, values, marker="o", color=INK, markerfacecolor="white")
    ax.set_xlabel("Number of clusters (k)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(ks)
    ax.grid(True, alpha=0.3, color="#bbbbbb")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / filename)
    plt.close(fig)


def _scatter(report: Report) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 5), dpi=150)
    for cluster in report["clusters"]:
        points = [
            p for p in report["projection"] if p["cluster_id"] == cluster["cluster_id"]
        ]
        marker, fill = CATEGORY_STYLES.get(cluster["category"], ("o", "#111111"))
        ax.scatter(
            [p["x"] for p in points],
            [p["y"] for p in points],
            s=16,
            alpha=0.65,
            marker=marker,
            facecolor=fill,
            edgecolor=INK,
            linewidth=0.4,
            label=f"{cluster['category']} (cluster {cluster['cluster_id']})",
        )
    ax.set_xlabel("PCA component 1")
    ax.set_ylabel("PCA component 2")
    ax.set_title("K-means clusters projected to 2D (PCA)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.3, color="#bbbbbb")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "pca_scatter.png")
    plt.close(fig)
