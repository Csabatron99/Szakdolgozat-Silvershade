from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.database.mongodb import get_database
from app.schemas.users import UpdateBalanceRequest, UpdateBalanceResponse
from app.services.deps import get_admin_user
from app.services.serializers import normalize_document, resolve_user_role

router = APIRouter(tags=["users"])


@router.get("/api/users")
async def list_users(_: Annotated[dict, Depends(get_admin_user)]):
    database = get_database()
    users = await database.users.find({}, {"password": 0, "password_hash": 0}).to_list(length=500)
    normalized_users = []
    for user in users:
        user["role"] = resolve_user_role(user)
        normalized_users.append(normalize_document(user))
    return normalized_users


@router.post("/api/users/update-balance", response_model=UpdateBalanceResponse)
async def update_balance(payload: UpdateBalanceRequest, _: Annotated[dict, Depends(get_admin_user)]):
    database = get_database()

    user = await database.users.find_one({"_id": ObjectId(payload.userId)})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_balance = float(user.get("balance", 0)) + payload.amount
    await database.users.update_one({"_id": user["_id"]}, {"$set": {"balance": new_balance}})

    return UpdateBalanceResponse(userId=payload.userId, balance=new_balance)
