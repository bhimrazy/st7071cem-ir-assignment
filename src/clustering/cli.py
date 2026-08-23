from __future__ import annotations

import argparse
import logging
import sys

from clustering import figures
from clustering.dataset import DOCUMENTS_PER_CATEGORY, load_corpus
from clustering.paths import FIGURES_DIR, MODEL_PATH, REPORT_PATH
from clustering.pipeline import EXAMPLE_DOCUMENTS, build

log = logging.getLogger("cluster")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fit and evaluate the clustering.")
    parser.add_argument(
        "--per-category",
        type=int,
        default=DOCUMENTS_PER_CATEGORY,
        help="documents to sample per category",
    )
    parser.add_argument(
        "--all", action="store_true", help="use every article instead of a sample"
    )
    parser.add_argument(
        "--no-figures", action="store_true", help="skip writing the plots"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    )

    log.info("loading corpus")
    corpus = load_corpus(per_category=None if args.all else args.per_category)
    log.info("loaded %d documents: %s", len(corpus), corpus.provenance.category_counts)
    log.info("source: %s", corpus.provenance.source)

    log.info("fitting TF-IDF and k-means")
    artifacts = build(corpus=corpus)
    model, report = artifacts.model, artifacts.report
    log.info(
        "fitted k=%d over a %d term vocabulary",
        report["k"],
        report["vocabulary_size"],
    )

    for cluster in report["clusters"]:
        log.info(
            "cluster %d is %s (n=%d): %s",
            cluster["cluster_id"],
            cluster["category"],
            cluster["size"],
            ", ".join(cluster["top_terms"]),
        )

    for point in report["elbow"]:
        log.info(
            "k=%d  inertia=%9.2f  silhouette=%+.4f  ARI=%.4f%s",
            point["k"],
            point["inertia"],
            point["silhouette"],
            point["adjusted_rand_index"],
            "  <- chosen" if point["k"] == report["k"] else "",
        )

    for name, value in report["metrics"].items():
        log.info("%-26s %.4f", name.replace("_", " "), value)

    confusion = report["confusion"]
    log.info("confusion matrix, rows are true and columns are assigned")
    log.info("%-16s%s", "", "".join(f"{c:>16}" for c in confusion["cols"]))
    for label, row in zip(confusion["rows"], confusion["matrix"], strict=True):
        log.info("%-16s%s", label, "".join(f"{v:>16}" for v in row))

    log.info("model written to %s", MODEL_PATH)
    log.info("report written to %s", REPORT_PATH)

    if not args.no_figures:
        figures.write_all(report)
        log.info("figures written to %s", FIGURES_DIR)

    for text in EXAMPLE_DOCUMENTS:
        assignment = model.predict(text)
        log.info(
            "%r -> %s (cluster %d, margin %.3f) on %s",
            text[:60] + "...",
            assignment.category,
            assignment.cluster_id,
            assignment.margin,
            ", ".join(assignment.matched_terms),
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
