from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.database.mongodb import get_database
from app.schemas.common import utc_now_iso
from app.schemas.transactions import BuyItemRequest, ConfirmTransactionRequest, CreateStoreItemRequest
from app.services.deps import get_admin_user, get_current_user, validate_service_api_key
from app.services.serializers import normalize_document

router = APIRouter(tags=["transactions"])


@router.post("/api/store/items")
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
    return normalize_document(document)


@router.get("/api/store/items")
async def get_store_items(current_user: Annotated[dict, Depends(get_current_user)]):
    _ = current_user
    database = get_database()
    items = await database.store_items.find({}).to_list(length=300)
    return [normalize_document(item) for item in items]


@router.post("/api/store/buy")
async def buy_store_item(payload: BuyItemRequest, current_user: Annotated[dict, Depends(get_current_user)]):
    database = get_database()

    item = await database.store_items.find_one({"_id": ObjectId(payload.itemId)})
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
    return normalize_document(transaction)


@router.get("/api/transactions")
async def list_transactions(current_user: Annotated[dict, Depends(get_current_user)]):
    database = get_database()

    query = {}
    if current_user.get("role") != "admin":
        query["userId"] = current_user["_id"]

    transactions = await database.transactions.find(query).to_list(length=500)
    return [normalize_document(transaction) for transaction in transactions]


@router.get("/api/pending-transactions")
async def pending_transactions(_: Annotated[str, Depends(validate_service_api_key)]):
    database = get_database()
    pending = await database.transactions.find({"status": "pending"}).to_list(length=500)
    return [normalize_document(tx) for tx in pending]


@router.get("/api/api/pending-transactions")
async def pending_transactions_legacy(_: Annotated[str, Depends(validate_service_api_key)]):
    return await pending_transactions(_)


@router.post("/api/confirm-transaction")
async def confirm_transaction(payload: ConfirmTransactionRequest, _: Annotated[str, Depends(validate_service_api_key)]):
    database = get_database()
    transaction = await database.transactions.find_one({"_id": ObjectId(payload.transactionId)})

    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    await database.transactions.update_one(
        {"_id": transaction["_id"]},
        {"$set": {"status": payload.status}},
    )

    updated = await database.transactions.find_one({"_id": transaction["_id"]})
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Transaction update failed")
    return normalize_document(updated)


@router.post("/api/api/confirm-transaction")
async def confirm_transaction_legacy(payload: ConfirmTransactionRequest, _: Annotated[str, Depends(validate_service_api_key)]):
    return await confirm_transaction(payload, _)
