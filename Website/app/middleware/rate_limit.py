import time
from collections import defaultdict, deque

from fastapi import HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config.settings import settings


class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.requests = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = settings.rate_limit_window_seconds
        bucket = self.requests[client_ip]

        while bucket and bucket[0] < now - window:
            bucket.popleft()

        if len(bucket) >= settings.rate_limit_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
            )

        bucket.append(now)
        return await call_next(request)
