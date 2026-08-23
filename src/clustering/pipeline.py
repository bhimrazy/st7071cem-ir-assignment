"""Everything expensive happens here rather than per request: the k sweep, the
silhouette scores, the PCA projection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sklearn.decomposition import PCA

from clustering.dataset import Corpus, load_corpus
from clustering.evaluate import DEFAULT_K_RANGE, EvaluationReport, evaluate
from clustering.model import DEFAULT_MODEL_PATH, ClusteringModel
from clustering.paths import REPORT_PATH

DEFAULT_REPORT_PATH = REPORT_PATH

# Offered in the UI so the assignment feature is testable without the user
# having to invent a news paragraph first. None appear in the training corpus.
EXAMPLE_DOCUMENTS: tuple[str, ...] = (
    (
        "The chancellor unveiled a budget aimed at curbing inflation, with the "
        "central bank expected to raise interest rates again before the end of "
        "the financial year."
    ),
    (
        "The actress accepted the award for best performance in a leading role, "
        "thanking the director and the cast of the film at a ceremony broadcast "
        "live to millions of viewers."
    ),
    (
        "Parliament passed the controversial bill after a lengthy debate, with "
        "the opposition accusing ministers of ignoring the results of the public "
        "consultation."
    ),
    (
        "Shares in the technology firm surged after it reported record quarterly "
        "profits and announced a share buyback worth several billion pounds."
    ),
)


@dataclass(slots=True)
class Artifacts:
    model: ClusteringModel
    report: dict[str, object]


def build(
    *,
    corpus: Corpus | None = None,
    k_range: range = DEFAULT_K_RANGE,
    model_path: Path = DEFAULT_MODEL_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    save: bool = True,
) -> Artifacts:
    corpus = corpus or load_corpus()
    model = ClusteringModel.fit(corpus.documents, corpus.labels)

    matrix = model.vectorizer.transform(corpus.documents)
    cluster_ids = [int(c) for c in model.kmeans.predict(matrix)]
    evaluation = evaluate(
        matrix,
        cluster_ids,
        model.kmeans,
        corpus.labels,
        model.cluster_to_category,
        k_range=k_range,
    )

    report = _build_report(corpus, model, cluster_ids, evaluation, matrix)

    if save:
        model.save(model_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return Artifacts(model=model, report=report)


def _build_report(
    corpus: Corpus,
    model: ClusteringModel,
    cluster_ids: list[int],
    evaluation: EvaluationReport,
    matrix,
) -> dict[str, object]:
    extrinsic = evaluation.extrinsic
    assert extrinsic is not None

    top_terms = model.top_terms_per_cluster(top_n=12)
    sizes = {cluster_id: cluster_ids.count(cluster_id) for cluster_id in top_terms}

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "corpus": {
            "total": len(corpus),
            "categories": list(corpus.categories),
            "counts": corpus.provenance.category_counts,
            "source": corpus.provenance.source,
            "original_source": corpus.provenance.original_source,
            "citation": corpus.provenance.citation,
            "licence_note": corpus.provenance.licence_note,
        },
        "vocabulary_size": len(model.vectorizer.get_feature_names_out()),
        "k": evaluation.chosen_k,
        "inertia": evaluation.inertia,
        "silhouette": evaluation.silhouette,
        "clusters": [
            {
                "cluster_id": cluster_id,
                "category": model.category_for_cluster(cluster_id),
                "size": sizes[cluster_id],
                "top_terms": terms,
            }
            for cluster_id, terms in sorted(top_terms.items())
        ],
        "elbow": [
            {
                "k": p.k,
                "inertia": p.inertia,
                "silhouette": p.silhouette,
                "adjusted_rand_index": p.adjusted_rand_index,
            }
            for p in evaluation.elbow_sweep
        ],
        "metrics": {
            "adjusted_rand_index": extrinsic.adjusted_rand_index,
            "normalized_mutual_info": extrinsic.normalized_mutual_info,
            "homogeneity": extrinsic.homogeneity,
            "completeness": extrinsic.completeness,
            "v_measure": extrinsic.v_measure,
            "accuracy": extrinsic.accuracy,
        },
        "confusion": {
            "rows": extrinsic.confusion_row_labels,
            "cols": extrinsic.confusion_col_labels,
            "matrix": extrinsic.confusion,
        },
        "projection": _project(matrix, cluster_ids, corpus.labels, model),
        "examples": list(EXAMPLE_DOCUMENTS),
    }


def _project(
    matrix, cluster_ids: list[int], true_labels: list[str], model: ClusteringModel
) -> list[dict[str, object]]:
    """2D PCA of the TF-IDF vectors, for the scatter plot.

    PCA rather than t-SNE: deterministic, so the figure in the report and the
    one in the UI are the same picture.
    """
    coords = PCA(n_components=2, random_state=model.random_state).fit_transform(
        matrix.toarray()
    )
    return [
        {
            "x": round(float(x), 4),
            "y": round(float(y), 4),
            "cluster_id": cluster_id,
            "category": model.category_for_cluster(cluster_id),
            "true_category": true_label,
        }
        for (x, y), cluster_id, true_label in zip(
            coords, cluster_ids, true_labels, strict=True
        )
    ]
