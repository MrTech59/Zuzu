"""Application error types and FastAPI error handling.

The API returns a consistent error envelope:

    {"error": {"code": "...", "message": "...", "detail": {...}}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ZuzuError(Exception):
    """Base class for expected, user-presentable errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "detail": self.detail,
            }
        }


class AuthError(ZuzuError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(ZuzuError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class NotFoundError(ZuzuError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ValidationError(ZuzuError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"


class ConflictError(ZuzuError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ProviderError(ZuzuError):
    """The AI provider failed or returned an invalid response."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "provider_error"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"


class ProviderAuthError(ProviderError):
    """Provider rejected our credentials. Never echoes the key."""

    status_code = status.HTTP_502_BAD_GATEWAY
    code = "provider_auth_error"


class PolicyDeniedError(ZuzuError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "policy_denied"


class ApprovalRequiredError(ZuzuError):
    status_code = status.HTTP_202_ACCEPTED
    code = "approval_required"


class MCPUnavailableError(ZuzuError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "mcp_unavailable"


class ToolArgumentError(ZuzuError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "tool_argument_error"


def install_error_handlers(app: FastAPI) -> None:
    """Attach consistent error handling to the app."""

    @app.exception_handler(ZuzuError)
    async def _zuzu_error(_: Request, exc: ZuzuError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_payload(),
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request payload failed validation.",
                    "detail": {"errors": exc.errors()},
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Log full detail; return generic message (no internals leak).
        import logging

        logging.getLogger("zuzu.api").exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Internal server error.",
                    "detail": {},
                }
            },
        )
