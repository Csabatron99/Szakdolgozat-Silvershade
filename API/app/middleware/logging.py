import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("silvershade")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "[%s] %s %s -> %s (%sms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response
