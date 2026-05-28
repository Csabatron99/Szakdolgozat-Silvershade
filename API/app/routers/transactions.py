from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from app.database.mongodb import get_database
from app.schemas.common import StatusUpdateRequest, paginate_response, success_response, utc_now_iso
from app.schemas.payments import TopupPackageRequest
from app.schemas.transactions import BuyItemRequest, CreateStoreItemRequest, UpdateStoreItemRequest
from app.services.deps import endpoint_rate_limit, get_admin_user, get_current_user, validate_service_api_key
from app.services.idempotency import cache_idempotency_response, get_cached_idempotency_response
from app.services.serializers import normalize_document

router = APIRouter(prefix="/api/v1", tags=["Transactions"])


@router.post(
    "/store/items",
    status_code=status.HTTP_201_CREATED,
    summary="Create a store item",
    description="Adds a new purchasable item to the store. `rewardData` is passed through to FiveM on delivery. **Admin only.**",
)
async def create_store_item(payload: CreateStoreItemRequest, _: Annotated[dict, Depends(get_admin_user)]):
    database = get_database()
    document = {
        "name": payload.name,
        "price": payload.price,
        "rewardData": payload.rewardData,
        "createdAt": utc_now_iso(),
    }
    result = await database.store_items.insert_one(document)
    document["_id"] = result.inserted_id
    return success_response(normalize_document(document))


# ── §4.5 Store Management ─────────────────────────────────────────────────────

@router.patch(
    "/store/items/{itemId}",
    summary="Update a store item",
    description="Partially update a store item's name, price, and/or rewardData. **Admin only.**",
)
async def update_store_item(
    itemId: str,
    payload: UpdateStoreItemRequest,
    _: Annotated[dict, Depends(get_admin_user)],
):
    database = get_database()
    try:
        item_id = ObjectId(itemId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item ID format")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided to update")

    updates["updatedAt"] = utc_now_iso()
    result = await database.store_items.find_one_and_update(
        {"_id": item_id},
        {"$set": updates},
        return_document=True,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store item not found")
    return success_response(normalize_document(result))


@router.delete(
    "/store/items/{itemId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a store item",
    description="Permanently removes a store item from the catalogue. **Admin only.**",
)
async def delete_store_item(
    itemId: str,
    _: Annotated[dict, Depends(get_admin_user)],
):
    database = get_database()
    try:
        item_id = ObjectId(itemId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item ID format")

    result = await database.store_items.delete_one({"_id": item_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store item not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/store/items",
    summary="List store items",
    description="Returns a paginated list of all available store items. Requires authentication.",
)
async def get_store_items(
    current_user: Annotated[dict, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    _ = current_user
    database = get_database()
    skip = (page - 1) * limit
    total = await database.store_items.count_documents({})
    items = await database.store_items.find({}).skip(skip).limit(limit).to_list(length=limit)
    return paginate_response([normalize_document(item) for item in items], total, page, limit)


@router.post(
    "/store/buy",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(endpoint_rate_limit(max_requests=20, window_seconds=60))],
    summary="Purchase a store item",
    description="Deducts the item price from the user's balance and creates a `pending` transaction. Send an `Idempotency-Key` header to safely retry without double-charging. Rate-limited to 20 requests/minute per user.",
)
async def buy_store_item(
    response: Response,
    payload: BuyItemRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
):
    if idempotency_key:
        cached = await get_cached_idempotency_response(idempotency_key, "buy_store_item")
        if cached:
            response.headers["Idempotent-Replayed"] = "true"
            return success_response(cached)

    database = get_database()

    try:
        item_id = ObjectId(payload.itemId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item ID format")

    item = await database.store_items.find_one({"_id": item_id})
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store item not found")

    price = float(item["price"])
    current_balance = float(current_user.get("balance", 0))
    if current_balance < price:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient balance")

    await database.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"balance": current_balance - price}},
    )

    transaction = {
        "userId": current_user["_id"],
        "type": "purchase",
        "amount": price,
        "status": "pending",
        "itemId": item["_id"],
        "rewardData": item.get("rewardData", {}),
        "createdAt": utc_now_iso(),
    }

    result = await database.transactions.insert_one(transaction)
    transaction["_id"] = result.inserted_id
    result_data = normalize_document(transaction)

    if idempotency_key:
        await cache_idempotency_response(idempotency_key, "buy_store_item", result_data)

    return success_response(result_data)


@router.get(
    "/transactions",
    summary="List transactions",
    description="Returns a paginated list of transactions. Regular users see only their own. Admins see all.",
)
async def list_transactions(
    current_user: Annotated[dict, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    database = get_database()
    query = {}
    if current_user.get("role") != "admin":
        query["userId"] = current_user["_id"]

    skip = (page - 1) * limit
    total = await database.transactions.count_documents(query)
    transactions = await database.transactions.find(query).sort("createdAt", -1).skip(skip).limit(limit).to_list(length=limit)
    return paginate_response([normalize_document(tx) for tx in transactions], total, page, limit)


@router.get(
    "/pending-transactions",
    summary="Get pending transactions",
    description="Returns all transactions with `status: pending`. Used by FiveM/Discord service clients to pick up work. **Requires service API key.**",
)
async def pending_transactions(_: Annotated[str, Depends(validate_service_api_key)]):
    database = get_database()
    pending = await database.transactions.find({"status": "pending"}).to_list(length=500)
    return success_response([normalize_document(tx) for tx in pending])


@router.patch(
    "/transactions/{transactionId}/status",
    summary="Update transaction status",
    description="Sets a transaction to `completed` or `pending`. Called by service clients after they have delivered the in-game reward. **Requires service API key.**",
)
async def confirm_transaction(
    transactionId: str,
    payload: StatusUpdateRequest,
    _: Annotated[str, Depends(validate_service_api_key)],
):
    database = get_database()

    try:
        tx_id = ObjectId(transactionId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid transaction ID format")

    transaction = await database.transactions.find_one({"_id": tx_id})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    await database.transactions.update_one(
        {"_id": transaction["_id"]},
        {"$set": {"status": payload.status}},
    )

    updated = await database.transactions.find_one({"_id": transaction["_id"]})
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Transaction update failed")
    return success_response(normalize_document(updated))


# ── §4.2 Top-up Packages — admin-configurable preset amounts ──────────────────

@router.get(
    "/topup-packages",
    summary="List top-up packages",
    description="Returns all admin-defined top-up packages sorted by amount ascending. Public endpoint — no auth required.",
)
async def list_topup_packages():
    database = get_database()
    packages = await database.topup_packages.find({}).sort("amount", 1).to_list(100)
    return success_response([normalize_document(p) for p in packages])


@router.post(
    "/admin/topup-packages",
    status_code=status.HTTP_201_CREATED,
    summary="Create a top-up package",
    description="Adds a new preset top-up package (e.g. 'Starter Pack — $10.00'). **Admin only.**",
)
async def create_topup_package(
    payload: TopupPackageRequest,
    _: Annotated[dict, Depends(get_admin_user)],
):
    database = get_database()
    doc = {
        "name": payload.name,
        "amount": payload.amount,
        "description": payload.description,
        "createdAt": utc_now_iso(),
    }
    result = await database.topup_packages.insert_one(doc)
    doc["_id"] = result.inserted_id
    return success_response(normalize_document(doc))


@router.delete(
    "/admin/topup-packages/{packageId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a top-up package",
    description="Removes a top-up package from the store. **Admin only.**",
)
async def delete_topup_package(
    packageId: str,
    _: Annotated[dict, Depends(get_admin_user)],
):
    database = get_database()
    try:
        pkg_id = ObjectId(packageId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid package ID format")

    result = await database.topup_packages.delete_one({"_id": pkg_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Package not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
