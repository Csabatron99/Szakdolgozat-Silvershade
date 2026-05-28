import json
import logging
from typing import Annotated
from urllib.error import URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends

from app.config.settings import settings
from app.database.mongodb import get_database
from app.schemas.common import utc_now_iso
from app.services.deps import get_admin_user, validate_service_api_key
from app.services.serializers import normalize_document

router = APIRouter(tags=["dashboard"])
logger = logging.getLogger("silvershade")


def _try_send_discord_webhook(message: str) -> bool:
    webhook_url = settings.discord_test_webhook_url.strip()
    if not webhook_url:
        return False

    payload = json.dumps({"content": message}).encode("utf-8")
    request = Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=6) as response:
            return 200 <= response.status < 300
    except URLError as error:
        logger.warning("Discord webhook send failed: %s", error)
        return False


@router.get("/api/dashboard/overview")
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

    return {
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
            "pendingTransactions": "/api/pending-transactions",
            "confirmTransaction": "/api/confirm-transaction",
            "adminActions": "/api/admin-actions",
            "confirmAdminAction": "/api/confirm-admin-action",
            "syncUpdates": "/api/sync/updates",
        },
    }


@router.get("/sync/updates")
@router.get("/api/sync/updates")
async def get_sync_updates(_: Annotated[str, Depends(validate_service_api_key)]):
    database = get_database()
    pending_transactions = await database.transactions.find({"status": "pending"}).sort("createdAt", 1).to_list(length=50)
    pending_admin_actions = await database.admin_actions.find({"status": "pending"}).sort("createdAt", 1).to_list(length=50)

    return {
        "generatedAt": utc_now_iso(),
        "pendingTransactions": [normalize_document(item) for item in pending_transactions],
        "pendingAdminActions": [normalize_document(item) for item in pending_admin_actions],
        "counts": {
            "pendingTransactions": len(pending_transactions),
            "pendingAdminActions": len(pending_admin_actions),
        },
    }


@router.post("/api/admin/simulate-fivem-rewards")
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

    return {
        "confirmed": len(pending),
        "type": "fivem-rewards",
        "message": f"FiveM dummy processed {len(pending)} reward(s).",
        "consolePreview": log_lines[:5],
    }


@router.post("/api/admin/simulate-fivem-actions")
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

    return {
        "confirmed": len(pending),
        "type": "fivem-actions",
        "message": f"FiveM dummy processed {len(pending)} admin action(s).",
        "consolePreview": log_lines[:5],
    }


@router.post("/api/admin/simulate-discord-pickup")
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

    return {
        "confirmed": len(pending),
        "type": "discord-pickup",
        "message": webhook_message,
        "webhookSent": webhook_sent,
    }
