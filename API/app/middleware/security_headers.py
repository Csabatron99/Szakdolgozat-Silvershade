from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security-related HTTP response headers to every response.
    These protect against common browser-based attacks (XSS, clickjacking,
    MIME sniffing, information leakage).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Prevent MIME-type sniffing attacks.
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Deny embedding this API in any iframe — prevents clickjacking.
        response.headers["X-Frame-Options"] = "DENY"

        # Legacy XSS filter for older browsers (belt-and-suspenders).
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Only send origin on cross-origin requests, full URL on same-origin.
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Swagger UI and ReDoc need to load scripts/styles (from CDN).
        # Every other path gets a strict 'none' policy.
        if request.url.path in ("/docs", "/redoc", "/openapi.json"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https://fastapi.tiangolo.com;"
            )
        else:
            # Pure JSON API routes — nothing to render in a browser.
            response.headers["Content-Security-Policy"] = "default-src 'none'"

        # Remove the Server header to avoid leaking implementation details.
        if "server" in response.headers:
            del response.headers["server"]

        return response
