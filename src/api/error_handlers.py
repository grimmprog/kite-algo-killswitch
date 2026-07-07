"""Exception handlers for the FastAPI application.

Implements consistent JSON error responses with request_id tracing.

Requirements covered:
- 4.2.3: Return 401, 403, 400, 500 with appropriate error responses
- 4.2.10: Include request_id in all responses for tracing
- 2.3.7: Log all errors with full context
"""

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def _get_request_id(request: Request) -> str:
    """Extract request_id from request state, falling back to 'unknown'."""
    return getattr(request.state, "request_id", "unknown")


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle HTTPException with consistent JSON response format.

    Returns JSON body with error message, status code, and request_id.
    """
    request_id = _get_request_id(request)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "request_id": request_id,
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle request validation errors with field-level detail.

    Returns 422 with a list of validation errors including field location,
    message, and the invalid value.
    """
    request_id = _get_request_id(request)

    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": " -> ".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation failed",
            "details": errors,
            "status_code": 422,
            "request_id": request_id,
        },
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Handle unhandled exceptions with a generic 500 response.

    Logs the full traceback for debugging while returning a safe error
    message to the client (no internal details leaked).
    """
    request_id = _get_request_id(request)

    logger.error(
        "Unhandled exception [request_id=%s] %s %s: %s\n%s",
        request_id,
        request.method,
        request.url.path,
        str(exc),
        traceback.format_exc(),
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "request_id": request_id,
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app instance."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
