"""Project-wide DRF exception handling.

Normalizes every error response to a consistent ``{ "error", "detail" }`` shape
so the frontend can render failures uniformly. Domain errors raised by the
service layer subclass :class:`AppError` and carry an HTTP status + message.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class AppError(Exception):
    """Base class for expected, user-facing application errors.

    Service-layer code raises these instead of returning ad-hoc responses so
    views stay thin and error formatting stays in one place.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    error = "bad_request"

    def __init__(self, detail: str, *, error: str | None = None, status_code: int | None = None):
        super().__init__(detail)
        self.detail = detail
        if error is not None:
            self.error = error
        if status_code is not None:
            self.status_code = status_code


class ValidationError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    error = "validation_error"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    error = "not_found"


class UnprocessableError(AppError):
    """Used e.g. when an LLM returns an invalid/uncompilable regex."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error = "unprocessable"


class LLMError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    error = "llm_error"


def api_exception_handler(exc, context):
    """Return uniform JSON for both AppError and standard DRF exceptions."""
    if isinstance(exc, AppError):
        return Response(
            {"error": exc.error, "detail": exc.detail},
            status=exc.status_code,
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        detail = response.data
        if isinstance(detail, dict) and "detail" in detail and len(detail) == 1:
            detail = detail["detail"]
        response.data = {"error": "request_error", "detail": detail}
        return response

    # Unhandled exception -> generic 500 (details go to logs, not the client).
    return Response(
        {"error": "server_error", "detail": "An unexpected error occurred."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
