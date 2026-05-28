import logging
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Optional Redis dependency — rate limiting works without it (falls back to in-memory).
try:
    import redis.asyncio as aioredis  # type: ignore[import-untyped]
    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False


class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window rate limiter.

    Uses Redis for persistent, distributed counters when ``REDIS_URL`` is
    configured and the ``redis`` package is installed.  Falls back to an
    in-process ``defaultdict(deque)`` automatically — no configuration
    required for local development.

    In-memory mode is reset on server restart and does not scale
    horizontally, but it is perfectly adequate for a single-instance
    deployment.
    """

    def __init__(self, app):
        super().__init__(app)
        self._redis: "aioredis.Redis | None" = None  # type: ignore[name-defined]
        self._memory: defaultdict[str, deque] = defaultdict(deque)
        # Latched to True after the first Redis connection failure so we stop
        # retrying on every request.
        self._redis_broken = False

    # ── Redis helpers ─────────────────────────────────────────────────────────

    async def _get_redis(self):
        """Return a live Redis client, or None if unavailable."""
        if self._redis_broken or not _REDIS_AVAILABLE or not settings.redis_url:
            return None
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1,
                )
                await self._redis.ping()
                logger.info("Rate limiter connected to Redis at %s", settings.redis_url)
            except Exception as exc:
                logger.warning(
                    "Redis unavailable (%s) — rate limiting falling back to in-memory", exc
                )
                self._redis = None
                self._redis_broken = True
        return self._redis

    # ── Core check ────────────────────────────────────────────────────────────

    async def _check_and_increment(
        self, key: str, now: float, window: int, limit: int
    ) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        redis_client = await self._get_redis()

        if redis_client is not None:
            # Sorted-set sliding window: member = timestamp, score = timestamp.
            redis_key = f"rl:{key}"
            try:
                pipe = redis_client.pipeline()
                # Remove entries outside the window.
                pipe.zremrangebyscore(redis_key, 0, now - window)
                # Count remaining entries (before this request).
                pipe.zcard(redis_key)
                # Record this request.
                pipe.zadd(redis_key, {str(now): now})
                # Auto-expire the key so Redis memory is reclaimed.
                pipe.expire(redis_key, window)
                results = await pipe.execute()
                count_before = results[1]
                return count_before < limit
            except Exception as exc:
                logger.warning("Redis error during rate-limit check (%s) — falling back", exc)
                self._redis_broken = True
                self._redis = None

        # ── In-memory fallback ────────────────────────────────────────────────
        bucket = self._memory[key]
        while bucket and bucket[0] < now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    # ── Middleware entry point ────────────────────────────────────────────────

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = settings.rate_limit_window_seconds
        limit = settings.rate_limit_requests

        allowed = await self._check_and_increment(client_ip, now, window, limit)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
                headers={"Retry-After": str(window)},
            )
        return await call_next(request)
