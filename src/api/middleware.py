"""Custom middleware for the FastAPI application.

Implements:
- Request ID middleware (adds X-Request-ID header for tracing)
- Request logging middleware (logs method, path, status, duration)

Requirements covered:
- 4.2.10: Include request_id in all responses for tracing
- 2.3.7: Log all errors with full context
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adds a unique X-Request-ID header to every response.

    If the incoming request already has an X-Request-ID header, it is preserved.
    Otherwise, a new UUID4 is generated. The request_id is stored in request.state
    for use by error handlers and other middleware.

    Also serves as the outermost exception boundary: any unhandled exception
    that propagates through call_next is caught here, logged, and returned
    as a 500 JSON response (Requirement 2.3.7, 4.2.3).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        import traceback

        from starlette.responses import JSONResponse as StarletteJSONResponse

        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception as exc:
            logger.error(
                "Unhandled exception [request_id=%s] %s %s: %s\n%s",
                request_id,
                request.method,
                request.url.path,
                str(exc),
                traceback.format_exc(),
            )
            response = StarletteJSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "status_code": 500,
                    "request_id": request_id,
                },
            )

        response.headers["X-Request-ID"] = request_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs every request with method, path, status code, and duration.

    Logs at INFO level for successful requests (2xx/3xx) and WARNING for
    client errors (4xx). Server errors (5xx) are logged by the error handler.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000
        request_id = getattr(request.state, "request_id", "unknown")

        log_data = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "request_id": request_id,
        }

        if response.status_code >= 500:
            logger.error("Request failed: %s", log_data)
        elif response.status_code >= 400:
            logger.warning("Client error: %s", log_data)
        else:
            logger.info("Request completed: %s", log_data)

        return response
