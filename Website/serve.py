"""
SilverShade Frontend Server
===========================
Serves HTML templates and static files.
Proxies all /api/* requests to the SilverShade API server so the browser
always talks to one origin — no CORS issues, httpOnly cookies work correctly.

Run:
    uvicorn serve:app --reload --host 127.0.0.1 --port 8080

Environment variables (.env):
    SILVERSHADE_API   URL of the API server  (default: http://127.0.0.1:8000)
    PORT              Port for this server   (default: 8080)
"""

import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic_settings import BaseSettings, SettingsConfigDict


class FrontendSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    silvershade_api: str = "http://127.0.0.1:8000"
    port: int = 8080


_settings = FrontendSettings()

# ── App ───────────────────────────────────────────────────────────────────────
# Disable docs — this server has no API of its own.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Headers that must not be forwarded blindly (they are managed by httpx/starlette).
_HOP_BY_HOP = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
}


# ── Reverse proxy ─────────────────────────────────────────────────────────────
@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_to_api(request: Request, path: str) -> Response:
    """Forward every /api/* request to the API server transparently."""
    body = await request.body()

    # Strip hop-by-hop headers before forwarding.
    forward_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP
    }

    async with httpx.AsyncClient(base_url=_settings.silvershade_api, timeout=30.0) as client:
        proxied = await client.request(
            method=request.method,
            url=f"/api/{path}",
            headers=forward_headers,
            content=body,
            params=dict(request.query_params),
            follow_redirects=False,
        )

    # Build the response — use media_type so content-type is set first.
    response = Response(
        content=proxied.content,
        status_code=proxied.status_code,
        media_type=proxied.headers.get("content-type"),
    )

    # Forward remaining response headers (handles multiple Set-Cookie correctly).
    _skip_response_headers = {"content-type", "content-encoding", "content-length", "transfer-encoding"}
    for header_name, header_value in proxied.headers.multi_items():
        if header_name.lower() not in _skip_response_headers:
            response.headers.append(header_name, header_value)

    return response


# ── HTML page routes ──────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/payment/success", response_class=HTMLResponse)
async def payment_success(request: Request):
    return templates.TemplateResponse("payment_success.html", {"request": request})


@app.get("/payment/cancel", response_class=HTMLResponse)
async def payment_cancel(request: Request):
    return templates.TemplateResponse("payment_cancel.html", {"request": request})


@app.get("/store", response_class=HTMLResponse)
async def store_page(request: Request):
    return templates.TemplateResponse("store.html", {"request": request})
