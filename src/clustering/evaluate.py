from __future__ import annotations

from dataclasses import dataclass, field

from scipy.sparse import spmatrix
from sklearn.cluster import KMeans
from sklearn.metrics import (
    adjusted_rand_score,
    completeness_score,
    confusion_matrix,
    homogeneity_score,
    normalized_mutual_info_score,
    silhouette_score,
    v_measure_score,
)

DEFAULT_K_RANGE = range(2, 9)


@dataclass(slots=True)
class ElbowPoint:
    k: int
    inertia: float
    silhouette: float
    # Agreement with the true categories at this k. Only available because
    # this corpus happens to be labelled; it is the sharpest signal we have
    # for whether a given k recovers the structure we care about.
    adjusted_rand_index: float | None = None


@dataclass(slots=True)
class ExtrinsicMetrics:
    """Agreement with the true categories.

    Every score here is permutation-invariant: k-means has no idea which
    cluster "should" have been numbered 0.
    """

    adjusted_rand_index: float
    normalized_mutual_info: float
    homogeneity: float
    completeness: float
    v_measure: float
    accuracy: float
    confusion: list[list[int]]
    confusion_row_labels: list[str]
    confusion_col_labels: list[str]


@dataclass(slots=True)
class EvaluationReport:
    chosen_k: int
    inertia: float
    silhouette: float
    elbow_sweep: list[ElbowPoint] = field(default_factory=list)
    extrinsic: ExtrinsicMetrics | None = None


def _fitted_inertia(model: KMeans) -> float:
    """`inertia_` is typed optional because it only exists after fitting."""
    if model.inertia_ is None:
        raise RuntimeError("KMeans has not been fitted")
    return float(model.inertia_)


def elbow_sweep(
    matrix: spmatrix,
    *,
    k_range: range = DEFAULT_K_RANGE,
    random_state: int = 42,
    true_labels: list[str] | None = None,
) -> list[ElbowPoint]:
    """Refit at each k, recording inertia, silhouette and (if known) ARI.

    Inertia falls monotonically with k, so it can only ever suggest an elbow,
    never a maximum. On sparse text silhouette stays close to zero at every k
    and barely moves, so neither is decisive here; pass `true_labels` and ARI
    gives a clear peak instead.
    """
    points: list[ElbowPoint] = []
    for k in k_range:
        model = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        cluster_ids = model.fit_predict(matrix)
        score = (
            silhouette_score(matrix, cluster_ids)
            if 2 <= k < matrix.shape[0]
            else float("nan")
        )
        points.append(
            ElbowPoint(
                k=k,
                inertia=_fitted_inertia(model),
                silhouette=float(score),
                adjusted_rand_index=(
                    float(adjusted_rand_score(true_labels, cluster_ids))
                    if true_labels is not None
                    else None
                ),
            )
        )
    return points


def extrinsic_metrics(
    cluster_ids: list[int],
    true_labels: list[str],
    cluster_to_category: dict[int, str],
) -> ExtrinsicMetrics:
    predicted = [cluster_to_category.get(c, str(c)) for c in cluster_ids]
    categories = sorted(set(true_labels))
    matrix = confusion_matrix(true_labels, predicted, labels=categories)
    agreed = sum(1 for t, p in zip(true_labels, predicted, strict=True) if t == p)

    return ExtrinsicMetrics(
        adjusted_rand_index=float(adjusted_rand_score(true_labels, cluster_ids)),
        normalized_mutual_info=float(
            normalized_mutual_info_score(true_labels, cluster_ids)
        ),
        homogeneity=float(homogeneity_score(true_labels, cluster_ids)),
        completeness=float(completeness_score(true_labels, cluster_ids)),
        v_measure=float(v_measure_score(true_labels, cluster_ids)),
        accuracy=agreed / len(true_labels) if true_labels else 0.0,
        confusion=matrix.tolist(),
        confusion_row_labels=categories,
        confusion_col_labels=categories,
    )


def evaluate(
    matrix: spmatrix,
    cluster_ids: list[int],
    kmeans: KMeans,
    true_labels: list[str],
    cluster_to_category: dict[int, str],
    *,
    k_range: range = DEFAULT_K_RANGE,
    random_state: int = 42,
) -> EvaluationReport:
    return EvaluationReport(
        chosen_k=kmeans.n_clusters,
        inertia=_fitted_inertia(kmeans),
        silhouette=float(silhouette_score(matrix, cluster_ids)),
        elbow_sweep=elbow_sweep(
            matrix,
            k_range=k_range,
            random_state=random_state,
            true_labels=true_labels,
        ),
        extrinsic=extrinsic_metrics(cluster_ids, true_labels, cluster_to_category),
    )
