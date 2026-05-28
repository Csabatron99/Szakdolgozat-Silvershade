from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

router = APIRouter(tags=["web"])

# Explicitly enable autoescaping for HTML templates (§1.4).
# Jinja2 does NOT enable autoescaping by default — this prevents XSS if any
# user-supplied data is ever rendered server-side.
_jinja_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html", "htm", "xml"]),
)
templates = Jinja2Templates(env=_jinja_env)


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def user_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@router.get("/payment/success", response_class=HTMLResponse)
async def payment_success(request: Request):
    return templates.TemplateResponse("payment_success.html", {"request": request})


@router.get("/payment/cancel", response_class=HTMLResponse)
async def payment_cancel(request: Request):
    return templates.TemplateResponse("payment_cancel.html", {"request": request})
