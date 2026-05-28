import hashlib
import hmac
import json
import logging
import time
from typing import Annotated
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends

from app.config.settings import settings
from app.database.mongodb import get_database
from app.schemas.common import success_response, utc_now_iso
from app.services.deps import get_admin_user, validate_service_api_key
from app.services.serializers import normalize_document

router = APIRouter(prefix="/api/v1", tags=["Dashboard"])
logger = logging.getLogger("silvershade")


def _try_send_discord_webhook(message: str) -> bool:
    """
    POST to the configured Discord test webhook URL.

    §1.7 — Webhook Security
    If ``WEBHOOK_SECRET`` is set, adds two extra headers so the receiver can
    verify authenticity:

    - ``X-SilverShade-Timestamp``: Unix timestamp (seconds, UTC)
    - ``X-SilverShade-Signature``: ``sha256=HMAC-SHA256(secret, timestamp + "." + body)``

    The timestamp is included in the signed payload to prevent replay attacks.
    """
    webhook_url = settings.discord_test_webhook_url.strip()
    if not webhook_url:
        return False

    payload = json.dumps({"content": message}).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    secret = settings.webhook_secret.strip()
    if secret:
        timestamp = str(int(time.time()))
        signed_body = (timestamp + ".").encode() + payload
        signature = hmac.new(secret.encode(), signed_body, hashlib.sha256).hexdigest()
        headers["X-SilverShade-Timestamp"] = timestamp
        headers["X-SilverShade-Signature"] = f"sha256={signature}"

    request = Request(
        webhook_url,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=6) as response:
            return 200 <= response.status < 300
    except URLError as error:
        logger.warning("Discord webhook send failed: %s", error)
        return False


@router.get(
    "/dashboard/overview",
    summary="Admin dashboard overview",
    description="Aggregated stats, recent activity, and service endpoint map used by the admin UI. **Admin only.**",
)
async def get_dashboard_overview(_: Annotated[dict, Depends(get_admin_user)]):
    database = get_database()

    users_count = await database.users.count_documents({})
    store_items_count = await database.store_items.count_documents({})
    pending_transactions_count = await database.transactions.count_documents({"status": "pending"})
    completed_transactions_count = await database.transactions.count_documents({"status": "completed"})
    pending_admin_actions_count = await database.admin_actions.count_documents({"status": "pending"})
    completed_admin_actions_count = await database.admin_actions.count_documents({"status": "completed"})

    pending_transactions = await database.transactions.find({"status": "pending"}).sort("createdAt", -1).to_list(length=10)
    pending_admin_actions = await database.admin_actions.find({"status": "pending"}).sort("createdAt", -1).to_list(length=10)
    recent_transactions = await database.transactions.find({}).sort("createdAt", -1).to_list(length=8)
    recent_admin_actions = await database.admin_actions.find({}).sort("createdAt", -1).to_list(length=8)

    return success_response({
        "generatedAt": utc_now_iso(),
        "stats": {
            "users": users_count,
            "storeItems": store_items_count,
            "pendingTransactions": pending_transactions_count,
            "completedTransactions": completed_transactions_count,
            "pendingAdminActions": pending_admin_actions_count,
            "completedAdminActions": completed_admin_actions_count,
        },
        "pendingTransactions": [normalize_document(item) for item in pending_transactions],
        "pendingAdminActions": [normalize_document(item) for item in pending_admin_actions],
        "recentTransactions": [normalize_document(item) for item in recent_transactions],
        "recentAdminActions": [normalize_document(item) for item in recent_admin_actions],
        "serviceEndpoints": {
            "pendingTransactions": "/api/v1/pending-transactions",
            "confirmTransaction": "/api/v1/transactions/{id}/status",
            "adminActions": "/api/v1/admin-actions",
            "confirmAdminAction": "/api/v1/admin-actions/{id}/status",
            "syncUpdates": "/api/v1/sync/updates",
        },
    })


@router.get(
    "/sync/updates",
    summary="Sync pending work",
    description="Single endpoint polled by FiveM and Discord clients. Returns all pending transactions and admin actions in one call. **Requires service API key.**",
)
async def get_sync_updates(_: Annotated[str, Depends(validate_service_api_key)]):
    database = get_database()
    # Exclude payment transactions — Stripe checkout completes them via webhook,
    # and legacy direct-purchase transactions are not FiveM-deliverable.
    # Only in-game reward transactions (type "reward") belong in the FiveM/Discord sync feed.
    _PAYMENT_TYPES = ("purchase", "stripe_checkout")
    pending_transactions = await database.transactions.find(
        {"status": "pending", "stripeSessionId": {"$exists": False}, "type": {"$nin": list(_PAYMENT_TYPES)}}
    ).sort("createdAt", 1).to_list(length=50)
    pending_admin_actions = await database.admin_actions.find({"status": "pending"}).sort("createdAt", 1).to_list(length=50)

    return success_response({
        "generatedAt": utc_now_iso(),
        "pendingTransactions": [normalize_document(item) for item in pending_transactions],
        "pendingAdminActions": [normalize_document(item) for item in pending_admin_actions],
        "counts": {
            "pendingTransactions": len(pending_transactions),
            "pendingAdminActions": len(pending_admin_actions),
        },
    })


@router.post(
    "/admin/simulate-fivem-rewards",
    summary="Simulate FiveM reward pickup",
    description="Development helper: marks all pending transactions as `completed`, simulating what the FiveM poller would do. **Admin only.**",
)
async def simulate_fivem_rewards(_: Annotated[dict, Depends(get_admin_user)]):
    """Mark all pending transactions as completed (simulates FiveM poller pickup)."""
    database = get_database()
    pending = await database.transactions.find({"status": "pending"}).to_list(length=500)
    log_lines = []

    for tx in pending:
        line = f"[FiveM Dummy] Rewarded user={tx.get('userId', '-')}, amount={tx.get('amount', 0)}"
        logger.info(line)
        log_lines.append(line)
        await database.transactions.update_one({"_id": tx["_id"]}, {"$set": {"status": "completed"}})

    if not pending:
        logger.info("[FiveM Dummy] No pending rewards in queue")

    return success_response({
        "confirmed": len(pending),
        "type": "fivem-rewards",
        "message": f"FiveM dummy processed {len(pending)} reward(s).",
        "consolePreview": log_lines[:5],
    })


@router.post(
    "/admin/simulate-fivem-actions",
    summary="Simulate FiveM action pickup",
    description="Development helper: marks all pending admin actions as `completed`, simulating FiveM server execution. **Admin only.**",
)
async def simulate_fivem_actions(_: Annotated[dict, Depends(get_admin_user)]):
    """Mark all pending admin actions as completed (simulates FiveM server pickup)."""
    database = get_database()
    pending = await database.admin_actions.find({"status": "pending"}).to_list(length=500)
    log_lines = []

    for action in pending:
        line = f"[FiveM Dummy] Executed action={action.get('type', '-')}, player={action.get('playerId', '-')}"
        logger.info(line)
        log_lines.append(line)
        await database.admin_actions.update_one({"_id": action["_id"]}, {"$set": {"status": "completed"}})

    if not pending:
        logger.info("[FiveM Dummy] No pending admin actions in queue")

    return success_response({
        "confirmed": len(pending),
        "type": "fivem-actions",
        "message": f"FiveM dummy processed {len(pending)} admin action(s).",
        "consolePreview": log_lines[:5],
    })


@router.post(
    "/admin/simulate-discord-pickup",
    summary="Simulate Discord bot pickup",
    description="Development helper: marks all pending admin actions as `completed` and fires the test Discord webhook if `DISCORD_TEST_WEBHOOK_URL` is set. **Admin only.**",
)
async def simulate_discord_pickup(_: Annotated[dict, Depends(get_admin_user)]):
    """Mark all pending admin actions as completed (simulates Discord bot pickup)."""
    database = get_database()
    pending = await database.admin_actions.find({"status": "pending"}).to_list(length=500)
    for action in pending:
        await database.admin_actions.update_one({"_id": action["_id"]}, {"$set": {"status": "completed"}})

    webhook_message = f"SilverShade test: Discord pickup simulated, confirmed {len(pending)} action(s)."
    webhook_sent = _try_send_discord_webhook(webhook_message)

    if webhook_sent:
        logger.info("Discord test webhook sent successfully")
    else:
        logger.info("Discord test webhook not sent (set DISCORD_TEST_WEBHOOK_URL to enable)")

    return success_response({
        "confirmed": len(pending),
        "type": "discord-pickup",
        "message": webhook_message,
        "webhookSent": webhook_sent,
    })


# ── §2.2 — API Changelog ──────────────────────────────────────────────────────

_CHANGELOG = [
    {
        "version": "1.0.0",
        "date": "2025-07-01",
        "summary": "Initial stable release.",
        "added": [
            "JWT auth with httpOnly cookies (POST /api/v1/auth/login).",
            "User registration and role management.",
            "Store items CRUD and purchase flow with idempotency keys.",
            "Admin actions queue (ban / kick / role) with FiveM/Discord confirm loop.",
            "Admin dashboard overview with aggregated stats.",
            "Single-call sync endpoint for service pollers (GET /api/v1/sync/updates).",
            "FiveM player state push (POST /api/v1/service/fivem/players).",
            "HMAC-SHA256 signing for outbound Discord webhooks (X-SilverShade-Signature).",
            "Scoped DB-backed API keys with SHA-256 hashing (POST /api/v1/admin/api-keys).",
            "Admin balance adjustment with credit transaction record.",
            "Full CORS, security-headers, per-endpoint rate limiting middleware.",
            "OpenAPI docs with field descriptions and per-endpoint summaries.",
        ],
        "changed": [],
        "removed": [],
    }
]


@router.get(
    "/changelog",
    summary="API changelog",
    description="Returns the API changelog as structured JSON, newest entry first.",
)
async def get_changelog():
    return success_response({"changelog": _CHANGELOG})
