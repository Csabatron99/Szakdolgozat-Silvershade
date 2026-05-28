import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.database.mongodb import close_mongo_connection, connect_to_mongo, get_database
from app.middleware.logging import LoggingMiddleware
from app.middleware.rate_limit import SimpleRateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routers.admin_actions import router as admin_actions_router
from app.routers.api_keys import router as api_keys_router
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.payments import router as payments_router
from app.routers.service import router as service_router
from app.routers.transactions import router as transactions_router
from app.routers.users import router as users_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("api.log", encoding="utf-8"),
    ],
)

# ── Startup security validation ──────────────────────────────────────────────
_WEAK_SECRETS = {"change-this-secret", "change-this-service-api-key", ""}


def _validate_secrets() -> None:
    if settings.secret_key in _WEAK_SECRETS or len(settings.secret_key) < 32:
        raise RuntimeError(
            "SECRET_KEY is not set or too weak. "
            "Set a random string of at least 32 characters in your .env file."
        )
    if settings.service_api_key in _WEAK_SECRETS:
        raise RuntimeError(
            "SERVICE_API_KEY is not set or still uses the default placeholder. "
            "Set a strong random key in your .env file."
        )


_validate_secrets()

# ── Parse allowed origins from comma-separated env var ───────────────────────
_allowed_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

# ── App ───────────────────────────────────────────────────────────────────────
from fastapi import FastAPI

_API_DESCRIPTION = """
## SilverShade REST API

Central backend for the **SilverShade** FiveM monetization and admin-control system.

### Clients
| Client | Role |
|--------|------|
| **Website** | Jinja2 frontend — all requests proxied via `/api/*` |
| **DiscordBot** | Node.js bot — polls sync endpoint, sends moderation commands |
| **FivemDummy** | Node.js FiveM stub — polls, confirms transactions and admin actions |

### Authentication
- **Users / Admins** — JWT stored in an `httpOnly` cookie set at `POST /api/v1/auth/login`
- **Service clients** — Bearer token via `Authorization: Bearer <SERVICE_API_KEY>`

### Versioning
All active routes live under `/api/v1/`. Legacy `/api/` paths return `308 Moved Permanently`.

Version identifiers are embedded in the **URL path** (e.g. `/api/v1/`) rather
than in `Accept` headers or query parameters.  Path-versioning was chosen
because:
- Browsers and curl can test it without custom headers
- Reverse proxies and CDNs can route by URL prefix without header inspection
- Bookmarkable and explicit for API consumers

When a breaking change requires `v2`, new routes will be added alongside `v1`
and `v1` will remain functional until all clients have migrated.

### API Keys
Service clients can authenticate with either the env-var `SERVICE_API_KEY`
(bootstrap / single-tenant) or with database-backed scoped keys managed at
`POST /api/v1/admin/api-keys`.  Scoped keys are stored as SHA-256 hashes.
"""

_OPENAPI_TAGS = [
    {"name": "Auth",           "description": "Registration, login, token refresh, and logout."},
    {"name": "Users",          "description": "User listing and balance management (admin only)."},
    {"name": "Transactions",   "description": "Store catalogue, item purchases, and transaction history."},
    {"name": "Admin Actions",  "description": "Queue and confirm in-game moderation commands (ban, kick, role)."},
    {"name": "Dashboard",      "description": "Admin dashboard overview and service sync endpoint."},
    {"name": "API Keys",       "description": "Manage scoped service API keys (§1.5). Admin only."},
    {"name": "Payments",       "description": "Stripe Checkout sessions, webhook receiver, and refunds (§3)."},
]

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=_API_DESCRIPTION,
    openapi_tags=_OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SimpleRateLimitMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Request-ID",
        "Idempotency-Key",
    ],
)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(transactions_router)
app.include_router(admin_actions_router)
app.include_router(dashboard_router)
app.include_router(service_router)
app.include_router(api_keys_router)
app.include_router(payments_router)


_HTTP_ERROR_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_SERVER_ERROR",
}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    from app.schemas.common import utc_now_iso
    code = _HTTP_ERROR_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": {"code": code, "message": exc.detail}, "meta": {"timestamp": utc_now_iso()}},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    from app.schemas.common import utc_now_iso
    # Pydantic v2 may include non-serializable ctx.error (raw ValueError) in exc.errors().
    # Normalize to safe primitives: loc, msg, type only.
    safe_errors = [
        {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"success": False, "error": {"code": "VALIDATION_ERROR", "message": "Request validation failed", "detail": safe_errors}, "meta": {"timestamp": utc_now_iso()}},
    )


@app.on_event("startup")
async def startup_event():
    connect_to_mongo()
    db = get_database()

    # Migrate any remaining plaintext passwords to bcrypt hashes.
    # Bcrypt hashes always start with "$2b$" or "$2a$"; anything else is plaintext.
    from app.services.security import hash_password as _hash
    async for user in db.users.find({"password": {"$exists": True}}):
        pwd = user.get("password", "")
        if isinstance(pwd, str) and pwd and not pwd.startswith(("$2b$", "$2a$")):
            await db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"password": _hash(pwd)}},
            )
            logging.getLogger(__name__).warning(
                "Migrated plaintext password for user %s to bcrypt hash.", str(user["_id"])
            )

    # Ensure indexes exist — idempotent, safe to run on every startup.
    await db.users.create_index("email", unique=True)
    await db.transactions.create_index([("userId", 1), ("status", 1), ("createdAt", -1)])
    await db.admin_actions.create_index([("status", 1), ("createdAt", -1)])
    await db.admin_actions.create_index("playerId")
    await db.store_items.create_index("name")
    # Idempotency cache: auto-expire entries after 24 hours, unique per (key, endpoint)
    await db.idempotency_cache.create_index("createdAt", expireAfterSeconds=86400)
    await db.idempotency_cache.create_index([("key", 1), ("endpoint", 1)], unique=True)
    # API keys — unique per hash so a rotated key cannot collide
    await db.api_keys.create_index("keyHash", unique=True)


@app.on_event("shutdown")
async def shutdown_event():
    close_mongo_connection()


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": settings.app_name, "version": "1.0.0"}


# ── Deprecated /api/ catch-all — must be last so v1 routes take precedence ───
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def deprecated_api_redirect(path: str, request: Request):
    new_path = f"/api/v1/{path}"
    qs = request.url.query
    location = f"{new_path}?{qs}" if qs else new_path
    return JSONResponse(
        status_code=308,
        content={
            "detail": (
                f"This endpoint has moved permanently to {new_path}. "
                "Please update your client to use /api/v1/ prefix."
            )
        },
        headers={
            "Location": location,
            "Deprecation": "true",
            "Sunset": "2027-01-01T00:00:00Z",
        },
    )
