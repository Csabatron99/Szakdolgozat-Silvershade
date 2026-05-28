import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config.settings import settings
from app.database.mongodb import close_mongo_connection, connect_to_mongo
from app.middleware.logging import LoggingMiddleware
from app.middleware.rate_limit import SimpleRateLimitMiddleware
from app.routers.admin_actions import router as admin_actions_router
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.transactions import router as transactions_router
from app.routers.users import router as users_router
from app.routers.web import router as web_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8"),
    ],
)

app = FastAPI(title=settings.app_name)

app.add_middleware(SimpleRateLimitMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(web_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(transactions_router)
app.include_router(admin_actions_router)
app.include_router(dashboard_router)


@app.on_event("startup")
async def startup_event():
    connect_to_mongo()


@app.on_event("shutdown")
async def shutdown_event():
    close_mongo_connection()


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}
