"""HTTP layer for both coursework tasks."""

from __future__ import annotations

from api.routes_clustering import router as clustering_router
from api.routes_search import router as search_router

__all__ = ["clustering_router", "search_router"]
