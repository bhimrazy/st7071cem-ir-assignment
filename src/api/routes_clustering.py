from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.dependencies import get_clustering_service
from api.models import ClassifyRequest, ClassifyResponse, ClusteringOverview
from clustering.service import ClusteringService

router = APIRouter(prefix="/api/clustering", tags=["clustering"])


@router.get("/overview", response_model=ClusteringOverview)
def overview(
    service: Annotated[ClusteringService, Depends(get_clustering_service)],
) -> dict[str, object]:
    """The corpus, the clusters, the metrics and the 2D projection."""
    return service.report


@router.post("/classify", response_model=ClassifyResponse)
def classify(
    service: Annotated[ClusteringService, Depends(get_clustering_service)],
    request: ClassifyRequest,
) -> ClassifyResponse:
    """Assign a document the model has never seen to its nearest cluster."""
    assignment = service.classify(request.text)
    return ClassifyResponse(
        category=assignment.category,
        cluster_id=assignment.cluster_id,
        distances=assignment.distances,
        margin=assignment.margin,
        matched_terms=assignment.matched_terms,
        matched_term_count=assignment.matched_term_count,
    )
