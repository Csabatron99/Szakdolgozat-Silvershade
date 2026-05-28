from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.database.mongodb import get_database
from app.schemas.common import paginate_response, success_response, utc_now_iso
from app.schemas.users import BalanceAdjustRequest, ChangePasswordRequest, LinkedAccountsRequest, RoleUpdateRequest, UpdateBalanceResponse
from app.services.deps import get_admin_user, get_current_user
from app.services.security import hash_password, verify_password
from app.services.serializers import normalize_document, resolve_user_role

router = APIRouter(prefix="/api/v1", tags=["Users"])


@router.get(
    "/users",
    summary="List all users",
    description="Returns a paginated list of all registered users. **Admin only.** Passwords are never returned. Optional `?search=` filters by email substring.",
)
async def list_users(
    _: Annotated[dict, Depends(get_admin_user)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
):
    database = get_database()
    skip = (page - 1) * limit
    query: dict = {}
    if search:
        import re
        query["email"] = {"$regex": re.escape(search), "$options": "i"}
    total = await database.users.count_documents(query)
    users = await database.users.find(query, {"password": 0, "password_hash": 0}).skip(skip).limit(limit).to_list(length=limit)
    for user in users:
        user["role"] = resolve_user_role(user)
    return paginate_response([normalize_document(u) for u in users], total, page, limit)


@router.patch(
    "/users/{userId}/balance",
    summary="Adjust a user's balance",
    description="Adds or subtracts an amount from the user's balance. Pass a negative `amount` to deduct. **Admin only.**",
)
async def update_balance(
    userId: str,
    payload: BalanceAdjustRequest,
    _: Annotated[dict, Depends(get_admin_user)],
):
    database = get_database()

    try:
        user_id = ObjectId(userId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")

    user = await database.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_balance = float(user.get("balance", 0)) + payload.amount
    await database.users.update_one({"_id": user["_id"]}, {"$set": {"balance": new_balance}})

    # §4.2 — record the balance change as a credit transaction for audit trail
    await database.transactions.insert_one({
        "userId": str(user["_id"]),
        "type": "credit",
        "amount": payload.amount,
        "status": "completed",
        "note": "Admin balance adjustment",
        "createdAt": utc_now_iso(),
    })

    return success_response(UpdateBalanceResponse(userId=userId, balance=new_balance).model_dump())


# ── §4.3 User: change own password ───────────────────────────────────────────
# NOTE: /users/me/* routes MUST be declared before /users/{userId}/* routes
# so FastAPI matches the literal "me" path before the parameterized one.

@router.patch(
    "/users/me/password",
    summary="Change own password",
    description="Authenticated user changes their own password. Requires current password for verification.",
)
async def change_own_password(
    payload: ChangePasswordRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    database = get_database()
    user = await database.users.find_one({"_id": current_user["_id"]})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    stored_hash = user.get("password") or user.get("password_hash") or ""
    if not verify_password(payload.currentPassword, stored_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")

    new_hash = hash_password(payload.newPassword)
    await database.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password": new_hash, "updatedAt": utc_now_iso()}},
    )
    return success_response({"message": "Password updated successfully"})


# ── §4.3 User: delete own account ────────────────────────────────────────────

@router.delete(
    "/users/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete own account",
    description="Authenticated user soft-deletes their own account. Sets `deletedAt` and clears the auth cookie.",
)
async def delete_own_account(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    from app.config.settings import settings

    database = get_database()
    await database.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"deletedAt": utc_now_iso()}},
    )
    resp = Response(status_code=204)
    resp.delete_cookie(key=settings.auth_cookie_name)
    return resp


# ── §4.3 User: update linked accounts ────────────────────────────────────────

@router.patch(
    "/users/me/linked-accounts",
    summary="Link Discord and FiveM accounts",
    description="Saves the user's Discord ID and FiveM player identifier. Pass `null` to unlink.",
)
async def update_linked_accounts(
    payload: LinkedAccountsRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    database = get_database()
    update: dict = {"updatedAt": utc_now_iso()}
    update["discordId"] = (payload.discordId or "").strip() or None
    update["fivemId"] = (payload.fivemId or "").strip() or None
    await database.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": update},
    )
    return success_response({
        "discordId": update["discordId"],
        "fivemId": update["fivemId"],
    })


# ── §4.4 Admin: change role ───────────────────────────────────────────────────

@router.patch(
    "/users/{userId}/role",
    summary="Change a user's role",
    description="Promote or demote a user between `user` and `admin`. **Admin only.**",
)
async def update_user_role(
    userId: str,
    payload: RoleUpdateRequest,
    admin: Annotated[dict, Depends(get_admin_user)],
):
    database = get_database()

    try:
        user_id = ObjectId(userId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")

    # Prevent an admin from demoting their own account via this endpoint.
    if str(admin["_id"]) == userId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change your own role via this endpoint")

    user = await database.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await database.users.update_one({"_id": user_id}, {"$set": {"role": payload.role, "updatedAt": utc_now_iso()}})
    updated = await database.users.find_one({"_id": user_id}, {"password": 0, "password_hash": 0})
    updated["role"] = resolve_user_role(updated)
    return success_response(normalize_document(updated))


# ── §4.4 Admin: soft-delete user ─────────────────────────────────────────────

@router.delete(
    "/users/{userId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user (admin)",
    description="Soft-deletes a user account by setting `deletedAt`. The record is retained for audit purposes. **Admin only.**",
)
async def admin_delete_user(
    userId: str,
    admin: Annotated[dict, Depends(get_admin_user)],
):
    database = get_database()

    try:
        user_id = ObjectId(userId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID format")

    if str(admin["_id"]) == userId:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account via admin endpoint")

    result = await database.users.update_one(
        {"_id": user_id, "deletedAt": {"$exists": False}},
        {"$set": {"deletedAt": utc_now_iso()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found or already deleted")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
