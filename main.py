"""main.py

FastAPI application entry point for the Smart Catering system.

This module wires together:
- API routes
- Rate limiting (SlowAPI)
- Basic health check endpoint
"""

from __future__ import annotations

from fastapi import FastAPI
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from slowapi.extension import _rate_limit_exceeded_handler

from api.routes import router as api_router


limiter = Limiter(key_func=get_remote_address, default_limits=["10/minute"])


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(title="Smart Catering Agent API", version="0.1.0")

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.include_router(api_router)

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Health check endpoint used by monitoring and local testing."""

        return {"status": "ok"}

    return app


app = create_app()
