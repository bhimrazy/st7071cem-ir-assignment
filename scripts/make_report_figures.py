"""Generate figures for the coursework report.

uv run python scripts/make_report_figures.py
"""

from __future__ import annotations

import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = pathlib.Path(__file__).resolve().parents[3] / "report" / "figures"

INK = "#1a1a1a"
MUTED = "#5a5a5a"
FILL_APP = "#eef3f8"
FILL_CORE = "#f4f0e8"
EDGE = "#8a97a6"


def box(ax, x, y, w, h, title, subtitle="", fill=FILL_APP):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.012,rounding_size=0.02",
            linewidth=1.1,
            edgecolor=EDGE,
            facecolor=fill,
        )
    )
    ax.text(
        x + w / 2,
        y + h * (0.62 if subtitle else 0.5),
        title,
        ha="center",
        va="center",
        fontsize=10.5,
        color=INK,
        weight="bold",
    )
    if subtitle:
        ax.text(
            x + w / 2,
            y + h * 0.28,
            subtitle,
            ha="center",
            va="center",
            fontsize=8.6,
            color=MUTED,
        )


def arrow(ax, start, end, label="", offset=0.0):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=13,
            linewidth=1.1,
            color=MUTED,
            shrinkA=2,
            shrinkB=2,
        )
    )
    if label:
        mx = (start[0] + end[0]) / 2 + offset
        my = (start[1] + end[1]) / 2
        ax.text(
            mx,
            my,
            label,
            ha="center",
            va="center",
            fontsize=8.2,
            color=MUTED,
            backgroundcolor="white",
        )


def architecture() -> None:
    fig, ax = plt.subplots(figsize=(9.2, 6.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7.4)
    ax.axis("off")

    box(ax, 0.4, 6.1, 2.6, 0.9, "pureportal", "CHCT web pages", "#f7f7f7")
    box(ax, 3.9, 6.1, 2.6, 0.9, "Polite crawler", "robots.txt, 5s delay", FILL_APP)
    box(ax, 7.4, 6.1, 2.2, 0.9, "Scheduler", "weekly re-crawl", FILL_APP)

    box(
        ax,
        0.4,
        4.5,
        9.2,
        1.0,
        "Collection  (documents + persistence)",
        "append-only log, compaction, background fsync",
        FILL_CORE,
    )

    box(ax, 0.4, 2.9, 2.9, 1.0, "Analyser", "tokenise, stopwords, stem", FILL_CORE)
    box(ax, 3.6, 2.9, 2.9, 1.0, "Inverted index", "term to postings", FILL_CORE)
    box(ax, 6.8, 2.9, 2.8, 1.0, "Ranking", "TF-IDF / BM25", FILL_CORE)

    box(ax, 1.6, 1.3, 3.2, 0.95, "FastAPI", "/api/search", FILL_APP)
    box(ax, 5.4, 1.3, 3.2, 0.95, "React interface", "Scholar-style results", FILL_APP)

    arrow(ax, (3.0, 6.55), (3.9, 6.55))
    arrow(ax, (7.4, 6.55), (6.5, 6.55))
    arrow(ax, (5.2, 6.1), (5.2, 5.5), "crawled documents", offset=1.35)
    arrow(ax, (1.9, 4.5), (1.9, 3.9))
    arrow(ax, (3.3, 3.4), (3.6, 3.4))
    arrow(ax, (6.5, 3.4), (6.8, 3.4))
    # Query path: interface -> API -> analyser -> index -> ranking -> interface
    arrow(ax, (5.4, 1.775), (4.8, 1.775), "query", offset=0.0)
    arrow(ax, (3.2, 2.25), (3.2, 2.9))
    arrow(ax, (8.2, 2.9), (7.6, 2.25), "ranked results", offset=1.15)

    ax.text(
        9.55,
        5.0,
        "miniseek\nengine core",
        fontsize=8.4,
        color=MUTED,
        ha="right",
        va="center",
        style="italic",
    )
    ax.text(
        0.42,
        0.72,
        "Indexing flows downward; a query flows upward through the same components.",
        fontsize=8.6,
        color=MUTED,
    )

    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "fig_architecture.png", dpi=220, bbox_inches="tight")
    plt.close(fig)
    print("wrote", OUT / "fig_architecture.png")


if __name__ == "__main__":
    architecture()
