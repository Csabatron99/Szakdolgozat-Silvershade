"""
Service-facing endpoints — authenticated with the SERVICE_API_KEY Bearer token.

These are used exclusively by internal service clients (Discord bot, FivemDummy).
They provide read access to store items, user profiles, and transactions,
plus the ability to adjust balances (for Discord bot admin commands)
and push FiveM player state (for the admin dashboard).
"""

from __future__ import annotations

from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database.mongodb import get_database
from app.schemas.admin_actions import CreateAdminActionRequest
from app.schemas.common import paginate_response, success_response, utc_now_iso
from app.schemas.users import BalanceAdjustRequest
from app.services.deps import get_admin_user, validate_service_api_key
from app.services.serializers import normalize_document, resolve_user_role

router = APIRouter(prefix="/api/v1/service", tags=["Service"])


@router.get(
    "/store",
    summary="List store items (service)",
    description="Returns all store items. Used by Discord bot `/store` command. **Requires service API key.**",
)
async def service_list_store(_: Annotated[str, Depends(validate_service_api_key)]):
    database = get_database()
    items = await database.store_items.find({}).to_list(length=100)
    return success_response([normalize_document(item) for item in items])


@router.get(
    "/users/discord/{discordId}",
    summary="Get user by Discord ID (service)",
    description="Look up a user by their linked Discord snowflake ID. **Requires service API key.**",
)
async def service_get_user_by_discord_id(
    discordId: str,
    _: Annotated[str, Depends(validate_service_api_key)],
):
    database = get_database()
    user = await database.users.find_one(
        {"discord_id": discordId},
        {"password": 0, "password_hash": 0, "hashed_password": 0},
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found for that Discord ID")
    user["role"] = resolve_user_role(user)
    return success_response(normalize_document(user))


@router.get(
    "/users/{userId}",
    summary="Get user by ID (service)",
    description="Returns a user's public profile including balance. **Requires service API key.**",
)
async def service_get_user(
    userId: str,
    _: Annotated[str, Depends(validate_service_api_key)],
):
    try:
        user_id = ObjectId(userId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")

    database = get_database()
    user = await database.users.find_one({"_id": user_id}, {"password": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user["role"] = resolve_user_role(user)
    return success_response(normalize_document(user))


@router.get(
    "/users/{userId}/transactions",
    summary="Get user transactions (service)",
    description="Returns recent transactions for a specific user. **Requires service API key.**",
)
async def service_get_user_transactions(
    userId: str,
    _: Annotated[str, Depends(validate_service_api_key)],
    limit: int = Query(10, ge=1, le=50),
):
    try:
        user_id = ObjectId(userId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")

    database = get_database()
    transactions = (
        await database.transactions.find({"userId": user_id})
        .sort("createdAt", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    return success_response([normalize_document(tx) for tx in transactions])


@router.patch(
    "/users/{userId}/balance",
    summary="Adjust user balance (service)",
    description="Adds or subtracts from a user's balance. Pass a negative `amount` to deduct. **Requires service API key.**",
)
async def service_adjust_balance(
    userId: str,
    payload: BalanceAdjustRequest,
    _: Annotated[str, Depends(validate_service_api_key)],
):
    try:
        user_id = ObjectId(userId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")

    database = get_database()
    user = await database.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_balance = float(user.get("balance", 0)) + payload.amount
    await database.users.update_one({"_id": user["_id"]}, {"$set": {"balance": new_balance}})
    return success_response({"userId": userId, "balance": new_balance, "updatedAt": utc_now_iso()})


# ── FiveM player state ────────────────────────────────────────────────────────

@router.post(
    "/fivem/players",
    summary="Push FiveM player list (service)",
    description=(
        "FivemDummy POSTs its current in-memory player list here on every poll cycle. "
        "The snapshot is stored in the `fivem_state` collection and served to the admin dashboard. "
        "**Requires service API key.**"
    ),
)
async def push_fivem_players(
    payload: dict,
    _: Annotated[str, Depends(validate_service_api_key)],
):
    players = payload.get("players", [])
    if not isinstance(players, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'players' must be a list")

    database = get_database()
    await database.fivem_state.replace_one(
        {"_id": "players"},
        {"_id": "players", "players": players, "updatedAt": utc_now_iso()},
        upsert=True,
    )
    return success_response({"pushed": len(players), "updatedAt": utc_now_iso()})


@router.get(
    "/fivem/players",
    summary="Get online FiveM players (admin)",
    description=(
        "Returns the latest player snapshot pushed by FivemDummy. "
        "Auto-refreshed by the admin dashboard every 10 seconds. **Admin only.**"
    ),
)
async def get_fivem_players(_: Annotated[dict, Depends(get_admin_user)]):
    database = get_database()
    state = await database.fivem_state.find_one({"_id": "players"})
    if not state:
        return success_response({"players": [], "updatedAt": None})
    return success_response({"players": state.get("players", []), "updatedAt": state.get("updatedAt")})


# ── Service admin actions (Discord bot / FivemDummy) ──────────────────────────

@router.post(
    "/admin-actions",
    status_code=status.HTTP_201_CREATED,
    summary="Queue admin action (service)",
    description=(
        "Allows service clients (Discord bot, FivemDummy) to queue ban/kick/role actions "
        "without needing admin JWT authentication. FiveM polls `/sync/updates` to pick them up. "
        "**Requires service API key.**"
    ),
)
async def service_create_admin_action(
    payload: CreateAdminActionRequest,
    _: Annotated[str, Depends(validate_service_api_key)],
):
    database = get_database()
    action = {
        "type": payload.type,
        "playerId": payload.playerId,
        "data": payload.data,
        "status": "pending",
        "createdAt": utc_now_iso(),
    }
    result = await database.admin_actions.insert_one(action)
    action["_id"] = result.inserted_id
    return success_response(normalize_document(action))


@router.get(
    "/transactions",
    summary="List recent transactions (service)",
    description="Returns recent transactions across all users. Used by Discord bot `!transactions` command. **Requires service API key.**",
)
async def service_list_transactions(
    _: Annotated[str, Depends(validate_service_api_key)],
    limit: int = Query(10, ge=1, le=50),
):
    database = get_database()
    transactions = (
        await database.transactions.find({})
        .sort("createdAt", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    return success_response([normalize_document(tx) for tx in transactions])

