"""Task 2: document clustering over BBC news (Economics, Entertainment, Politics)."""

from __future__ import annotations

from clustering.dataset import CATEGORIES, Corpus, Provenance, load_corpus
from clustering.evaluate import (
    ElbowPoint,
    EvaluationReport,
    ExtrinsicMetrics,
    elbow_sweep,
    evaluate,
    extrinsic_metrics,
)
from clustering.model import ClusterAssignment, ClusteringModel
from clustering.pipeline import EXAMPLE_DOCUMENTS, Artifacts, build
from clustering.service import ClusteringService

__all__ = [
    "CATEGORIES",
    "EXAMPLE_DOCUMENTS",
    "Artifacts",
    "ClusterAssignment",
    "ClusteringModel",
    "ClusteringService",
    "Corpus",
    "ElbowPoint",
    "EvaluationReport",
    "ExtrinsicMetrics",
    "Provenance",
    "build",
    "elbow_sweep",
    "evaluate",
    "extrinsic_metrics",
    "load_corpus",
]
