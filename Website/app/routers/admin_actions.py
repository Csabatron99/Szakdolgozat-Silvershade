from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.database.mongodb import get_database
from app.schemas.admin_actions import ConfirmAdminActionRequest, CreateAdminActionRequest
from app.schemas.common import utc_now_iso
from app.services.deps import get_admin_user, validate_service_api_key
from app.services.serializers import normalize_document

router = APIRouter(tags=["admin-actions"])


@router.post("/api/create-admin-action")
async def create_admin_action(payload: CreateAdminActionRequest, _: Annotated[dict, Depends(get_admin_user)]):
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
    return normalize_document(action)


@router.get("/api/admin-actions")
async def get_pending_admin_actions(_: Annotated[str, Depends(validate_service_api_key)]):
    database = get_database()
    actions = await database.admin_actions.find({"status": "pending"}).to_list(length=500)
    return [normalize_document(action) for action in actions]


@router.get("/api/api/admin-actions")
async def get_pending_admin_actions_legacy(_: Annotated[str, Depends(validate_service_api_key)]):
    return await get_pending_admin_actions(_)


@router.get("/api/admin-actions/history")
async def get_admin_actions_history(_: Annotated[dict, Depends(get_admin_user)]):
    database = get_database()
    actions = await database.admin_actions.find({}).sort("createdAt", -1).to_list(length=200)
    return [normalize_document(action) for action in actions]


@router.post("/api/confirm-admin-action")
async def confirm_admin_action(payload: ConfirmAdminActionRequest, _: Annotated[str, Depends(validate_service_api_key)]):
    database = get_database()
    action = await database.admin_actions.find_one({"_id": ObjectId(payload.actionId)})

    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin action not found")

    await database.admin_actions.update_one(
        {"_id": action["_id"]},
        {"$set": {"status": payload.status}},
    )

    updated = await database.admin_actions.find_one({"_id": action["_id"]})
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Admin action update failed")
    return normalize_document(updated)


@router.post("/api/api/confirm-admin-action")
async def confirm_admin_action_legacy(payload: ConfirmAdminActionRequest, _: Annotated[str, Depends(validate_service_api_key)]):
    return await confirm_admin_action(payload, _)
