"""API dependencies: authentication and settings access.

Authentication design (v0.1.0):
- All /api/v1 endpoints except /api/v1/health require a Bearer token.
- The token is compared against settings.zuzu_api_key (constant-time compare).
- Auth is enforced when ZUZU_API_KEY is set, or whenever APP_ENV is not a
  development environment. An unset key + development env is tolerated for
  localhost-only development and logs a warning at startup.
- An internal IP address is never treated as authentication.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import Depends, Request

from zuzu.config import Settings, get_settings
from zuzu.errors import AuthError

logger = logging.getLogger("zuzu.auth")

PUBLIC_PATHS = {"/api/v1/health"}


def verify_token(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


async def require_auth(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """FastAPI dependency enforcing bearer-token auth on API routes."""
    if request.url.path in PUBLIC_PATHS:
        return

    if not settings.auth_enforced:
        # Development mode with no configured key: allow, but loudly note it.
        return

    expected = settings.zuzu_api_key or ""
    header = request.headers.get("authorization", "")
    provided = None
    if header.lower().startswith("bearer "):
        provided = header[7:].strip()

    if not verify_token(provided, expected):
        raise AuthError("Missing or invalid bearer token.")
