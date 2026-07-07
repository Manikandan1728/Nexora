"""
api/dependencies.py — FastAPI dependency providers for Phase 7.

All ``Depends(...)`` targets live here.  The app initialises expensive
resources once in ``lifespan`` and stores them in ``app.state``; these
functions retrieve them from state so routes and services never construct
new instances per-request.
"""

from __future__ import annotations

from fastapi import Request

from api.config import APISettings, get_settings


def get_api_settings(request: Request) -> APISettings:
    """
    Return the shared ``APISettings`` instance stored on ``app.state``.

    Falls back to the module-level singleton if state is not set (e.g.
    during unit tests that don't go through lifespan).

    Args:
        request: The current FastAPI ``Request`` (injected automatically).

    Returns:
        The shared ``APISettings`` singleton.
    """
    try:
        return request.app.state.settings
    except AttributeError:
        return get_settings()
