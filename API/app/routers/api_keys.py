"""
API Key management — §1.5
=========================
Admins can create scoped service API keys stored in MongoDB (hashed with
SHA-256).  The raw key is shown only once at creation / rotation time.

Backward compatibility:  the legacy ``SERVICE_API_KEY`` env-var key still
works — it is checked first in ``validate_service_api_key`` in deps.py.
"""

import hashlib
import secrets
from typing import Annotated

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.database.mongodb import get_database
from app.schemas.api_keys import VALID_SCOPES, CreateApiKeyRequest
from app.schemas.common import success_response, utc_now_iso
from app.services.deps import get_admin_user
from app.services.serializers import normalize_document

router = APIRouter(prefix="/api/v1/admin/api-keys", tags=["API Keys"])


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
    description=(
        "Generates a new scoped service API key. "
        "**The raw key value is shown exactly once** — copy it immediately. "
        "Only the SHA-256 hash is stored. **Admin only.**"
    ),
)
async def create_api_key(
    payload: CreateApiKeyRequest,
    _: Annotated[dict, Depends(get_admin_user)],
):
    invalid = set(payload.scopes) - VALID_SCOPES
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scope(s): {', '.join(sorted(invalid))}. Valid: {', '.join(sorted(VALID_SCOPES))}",
        )

    raw_key = secrets.token_hex(32)  # 64-char hex string
    database = get_database()
    doc = {
        "name": payload.name,
        "scopes": payload.scopes,
        "keyHash": _hash_key(raw_key),
        "createdAt": utc_now_iso(),
        "lastUsedAt": None,
    }
    result = await database.api_keys.insert_one(doc)
    doc["_id"] = result.inserted_id

    response = normalize_document(doc)
    del response["keyHash"]        # never expose the hash
    response["key"] = raw_key     # shown once — store it now
    return success_response(response)


@router.get(
    "",
    summary="List API keys",
    description="Returns metadata for all API keys. Hashes are never included. **Admin only.**",
)
async def list_api_keys(_: Annotated[dict, Depends(get_admin_user)]):
    database = get_database()
    # projection {"keyHash": 0} hides the hash; fake DB ignores projections but that's fine for tests
    keys = await database.api_keys.find({}, {"keyHash": 0}).to_list(length=200)
    return success_response([normalize_document(k) for k in keys])


@router.delete(
    "/{keyId}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
    description="Permanently deletes an API key. Clients using it lose access immediately. **Admin only.**",
)
async def revoke_api_key(
    keyId: str,
    _: Annotated[dict, Depends(get_admin_user)],
):
    try:
        oid = ObjectId(keyId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid key ID format")

    database = get_database()
    result = await database.api_keys.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")


@router.post(
    "/{keyId}/rotate",
    summary="Rotate an API key",
    description=(
        "Generates a new value for an existing key entry. "
        "The old value is invalidated immediately. "
        "**New key shown only once.** Admin only."
    ),
)
async def rotate_api_key(
    keyId: str,
    _: Annotated[dict, Depends(get_admin_user)],
):
    try:
        oid = ObjectId(keyId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid key ID format")

    database = get_database()
    key_doc = await database.api_keys.find_one({"_id": oid})
    if not key_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    raw_key = secrets.token_hex(32)
    await database.api_keys.update_one(
        {"_id": oid},
        {"$set": {"keyHash": _hash_key(raw_key), "rotatedAt": utc_now_iso()}},
    )

    response = normalize_document(key_doc)
    response.pop("keyHash", None)   # never expose
    response["key"] = raw_key       # shown once
    return success_response(response)
