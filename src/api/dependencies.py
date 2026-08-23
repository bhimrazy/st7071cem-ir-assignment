"""Request-scoped access to the objects the app owns.

Both are created once in `main.py`'s lifespan and hung off `app.state`, so
routes reach them through a dependency rather than a module-level global and
tests can inject their own.
"""

from __future__ import annotations

from fastapi import Request

from clustering.service import ClusteringService
from miniseek.collection import Collection


def get_collection(request: Request) -> Collection:
    return request.app.state.collection


def get_clustering_service(request: Request) -> ClusteringService:
    return request.app.state.clustering
