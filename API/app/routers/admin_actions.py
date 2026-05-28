from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.database.mongodb import get_database
from app.schemas.admin_actions import CreateAdminActionRequest
from app.schemas.common import StatusUpdateRequest, paginate_response, success_response, utc_now_iso
from app.services.deps import get_admin_user, validate_service_api_key
from app.services.serializers import normalize_document

router = APIRouter(prefix="/api/v1", tags=["Admin Actions"])


@router.post(
    "/admin-actions",
    status_code=status.HTTP_201_CREATED,
    summary="Queue an admin action",
    description="Creates a pending moderation command (ban, kick, give_role, remove_role) targeting a FiveM player. The FiveM service picks it up via `/sync/updates`. **Admin only.**",
)
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
    return success_response(normalize_document(action))


@router.get(
    "/admin-actions",
    summary="Get pending admin actions",
    description="Returns all admin actions with `status: pending`. Polled by FiveM and Discord service clients. **Requires service API key.**",
)
async def get_pending_admin_actions(_: Annotated[str, Depends(validate_service_api_key)]):
    database = get_database()
    actions = await database.admin_actions.find({"status": "pending"}).to_list(length=500)
    return success_response([normalize_document(action) for action in actions])


@router.get(
    "/admin-actions/history",
    summary="Full admin action history",
    description="Returns a paginated list of all admin actions (any status), sorted newest first. **Admin only.**",
)
async def get_admin_actions_history(
    _: Annotated[dict, Depends(get_admin_user)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    database = get_database()
    skip = (page - 1) * limit
    total = await database.admin_actions.count_documents({})
    actions = await database.admin_actions.find({}).sort("createdAt", -1).skip(skip).limit(limit).to_list(length=limit)
    return paginate_response([normalize_document(a) for a in actions], total, page, limit)


@router.patch(
    "/admin-actions/{actionId}/status",
    summary="Update admin action status",
    description="Marks an admin action as `completed` after the FiveM/Discord client has executed it. **Requires service API key.**",
)
async def confirm_admin_action(
    actionId: str,
    payload: StatusUpdateRequest,
    _: Annotated[str, Depends(validate_service_api_key)],
):
    database = get_database()

    try:
        action_id = ObjectId(actionId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action ID format")

    action = await database.admin_actions.find_one({"_id": action_id})
    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin action not found")

    await database.admin_actions.update_one(
        {"_id": action["_id"]},
        {"$set": {"status": payload.status}},
    )

    updated = await database.admin_actions.find_one({"_id": action["_id"]})
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Admin action update failed")
    return success_response(normalize_document(updated))
