"""SPA handler for serving React frontend from FastAPI.

This module provides routing configuration to serve a Single Page Application (SPA)
from FastAPI. It handles:
- Static asset serving at /ui/assets/*
- Catch-all routing for client-side navigation
- Graceful fallback when frontend build is not present
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


logger = logging.getLogger(__name__)


def setup_spa_routes(app: FastAPI, frontend_path: Path | None = None) -> None:
    """Configure SPA routes for serving the React frontend.

    This function sets up routes to serve the built React application from FastAPI.
    It must be called AFTER all API routes are registered to ensure API endpoints
    take precedence over the catch-all SPA route.

    Args:
        app: The FastAPI application instance.
        frontend_path: Path to the frontend dist directory. Defaults to
            {project_root}/frontend/dist.

    Note:
        - Static assets are mounted at /ui/assets BEFORE catch-all routes
        - Catch-all route serves index.html for React Router compatibility
        - If dist folder doesn't exist, routes are not registered (graceful degradation)
    """
    if frontend_path is None:
        frontend_path = Path(__file__).parent.parent / "frontend" / "dist"

    # Check if frontend build exists
    if not frontend_path.exists():
        logger.warning(
            "Frontend dist folder not found at %s. SPA routes not configured. "
            "Run 'bun run build:ui' to build the frontend.",
            frontend_path,
        )
        return

    index_path = frontend_path / "index.html"
    if not index_path.exists():
        logger.error(
            "index.html not found in frontend dist at %s. SPA routes not configured.",
            frontend_path,
        )
        return

    # Mount static assets BEFORE catch-all routes
    # This ensures /ui/assets/* requests serve actual files, not index.html
    assets_path = frontend_path / "assets"
    if assets_path.exists():
        app.mount(
            "/ui/assets",
            StaticFiles(directory=assets_path),
            name="spa_assets",
        )
        logger.info("Mounted SPA assets at /ui/assets from %s", assets_path)

    # Serve index.html for root UI routes
    @app.get("/ui", include_in_schema=False)
    async def serve_spa_root() -> FileResponse:
        """Serve index.html for /ui route."""
        return FileResponse(index_path)

    @app.get("/ui/", include_in_schema=False)
    async def serve_spa_root_trailing() -> FileResponse:
        """Serve index.html for /ui/ route with trailing slash."""
        return FileResponse(index_path)

    # Catch-all route for client-side routing
    # This must be registered AFTER static mounts and specific routes
    @app.get("/ui/{path:path}", include_in_schema=False)
    async def serve_spa_catch_all(path: str) -> FileResponse:
        """Serve static files or index.html for React Router routes.

        For any path under /ui/:
        - If the path matches an existing file in dist, serve that file
        - Otherwise, serve index.html for client-side routing

        Args:
            path: The requested path relative to /ui/

        Returns:
            FileResponse with the requested file or index.html
        """
        # Check if path matches an actual file in the dist folder
        requested_file = frontend_path / path
        if requested_file.exists() and requested_file.is_file():
            return FileResponse(requested_file)

        # Serve index.html for all other routes (React Router handles client-side)
        return FileResponse(index_path)

    logger.info("SPA routes configured at /ui from %s", frontend_path)
