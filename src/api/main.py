"""The only module that knows about both tasks. It mounts their routers behind one
origin so the UI can switch between them without a second deployment.

Vite serves the frontend in development and proxies /api here. After
`npm run build` this app serves frontend/dist itself."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from api.routes_clustering import router as clustering_router
from api.routes_search import router as search_router
from clustering.service import ClusteringService
from miniseek.collection import Collection
from publications import open_publications

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(
    *,
    collection: Collection | None = None,
    clustering: ClusteringService | None = None,
) -> FastAPI:
    """Build the app, optionally with pre-built dependencies injected by tests."""
    owns_collection = collection is None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # `collection is None`, not `collection or ...`: Collection defines
        # __len__, so an *empty* injected collection is falsy and `or` would
        # silently discard it and open the real crawled corpus instead.
        app.state.collection = open_publications() if collection is None else collection
        # The clustering model loads lazily on first use, so startup stays fast
        # even when the fitted artefacts are missing and need rebuilding.
        app.state.clustering = clustering or ClusteringService()
        try:
            yield
        finally:
            if owns_collection:
                app.state.collection.close()

    app = FastAPI(
        title="ST7071CEM Information Retrieval Coursework",
        description=(
            "Task 1: vertical search over publications by members of Coventry "
            "University's Centre for Healthcare and Community Transformation. "
            "Task 2: document clustering over BBC news."
        ),
        version="0.2.0",
        lifespan=lifespan,
    )

    app.include_router(search_router)
    app.include_router(clustering_router)

    if FRONTEND_DIST.is_dir():
        app.frontend("/", directory=FRONTEND_DIST)

    return app


app = create_app()
