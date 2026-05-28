import hashlib
from collections import defaultdict, deque
from collections.abc import Callable
from time import monotonic

from bson import ObjectId
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import settings
from app.database.mongodb import get_database
from app.services.security import decode_access_token
from app.services.serializers import resolve_user_role

jwt_scheme = HTTPBearer(auto_error=False)

# ── Per-endpoint rate limiting ────────────────────────────────────────────────
# Separate buckets per endpoint key so a burst on /login doesn't affect /buy.
_endpoint_buckets: dict[str, dict[str, deque]] = defaultdict(lambda: defaultdict(deque))


def endpoint_rate_limit(max_requests: int, window_seconds: int) -> Callable:
    """
    Returns a FastAPI dependency that enforces a per-IP rate limit scoped to
    the endpoint it is applied on.

    Usage:
        @router.post("/login", dependencies=[Depends(endpoint_rate_limit(10, 60))])
    """

    def _check(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        # Use the URL path as the bucket key so limits are per-endpoint.
        bucket_key = request.url.path
        bucket = _endpoint_buckets[bucket_key][client_ip]
        now = monotonic()

        # Evict timestamps outside the current window.
        while bucket and bucket[0] < now - window_seconds:
            bucket.popleft()

        if len(bucket) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests — please slow down.",
                headers={"Retry-After": str(window_seconds)},
            )

        bucket.append(now)

    return _check


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(jwt_scheme),
    auth_cookie: str | None = Cookie(default=None, alias=settings.auth_cookie_name),
) -> dict:
    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif auth_cookie:
        token = auth_cookie

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")

    payload = decode_access_token(token)
    database = get_database()
    user = await database.users.find_one({"_id": ObjectId(payload["sub"])})

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    user["role"] = resolve_user_role(user)

    return user


def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    if resolve_user_role(current_user) != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def validate_service_api_key(authorization: str | None = Header(default=None)) -> str:
    """
    Accepts service Bearer tokens.  Checks in order:

    1. Env-var ``SERVICE_API_KEY`` — backward compat / bootstrap key.
    2. Database-backed keys stored as SHA-256 hashes in the ``api_keys``
       collection (managed via POST /api/v1/admin/api-keys).

    §1.5 — API Key Scopes
    """
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        ) from exc

    if scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization scheme")

    # 1. Fast path: check the single env-var key for backward compatibility.
    if token == settings.service_api_key:
        return token

    # 2. Check database-backed hashed keys.
    key_hash = hashlib.sha256(token.encode()).hexdigest()
    database = get_database()
    key_doc = await database.api_keys.find_one({"keyHash": key_hash})
    if not key_doc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return token
