import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.config.settings import settings
from app.database.mongodb import get_database
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.schemas.common import utc_now_iso
from app.services.deps import get_current_user
from app.services.security import create_access_token, hash_password, verify_password
from app.services.serializers import resolve_user_role

router = APIRouter(prefix="/api/auth", tags=["auth"])


async def _verify_and_normalize_password(database, user: dict, plain_password: str) -> bool:
    stored_password = user.get("password") or user.get("password_hash") or ""
    if not isinstance(stored_password, str) or not stored_password:
        return False

    try:
        password_valid = verify_password(plain_password, stored_password)
        if password_valid and not user.get("password"):
            await database.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"password": hash_password(plain_password)}},
            )
        return password_valid
    except Exception:
        # Legacy records may still store plaintext passwords.
        password_valid = secrets.compare_digest(plain_password, stored_password)
        if password_valid:
            await database.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"password": hash_password(plain_password)}},
            )
        return password_valid


@router.post("/register", response_model=UserResponse)
async def register(payload: RegisterRequest):
    database = get_database()
    existing = await database.users.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    document = {
        "email": payload.email.lower(),
        "password": hash_password(payload.password),
        "role": "user",
        "balance": 0.0,
        "createdAt": utc_now_iso(),
    }

    result = await database.users.insert_one(document)
    return UserResponse(
        id=str(result.inserted_id),
        email=document["email"],
        role=document["role"],
        balance=document["balance"],
        createdAt=document["createdAt"],
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response):
    database = get_database()
    user = await database.users.find_one({"email": payload.email.lower()})

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    password_valid = await _verify_and_normalize_password(database, user, payload.password)

    if not password_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    role = resolve_user_role(user)

    await database.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "role": role,
                "balance": float(user.get("balance", 0.0)),
                "createdAt": user.get("createdAt", utc_now_iso()),
            },
        },
    )

    token = create_access_token(subject=str(user["_id"]), role=role)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        max_age=settings.access_token_expire_minutes * 60,
    )
    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=settings.auth_cookie_name, httponly=True, samesite="lax")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: Annotated[dict, Depends(get_current_user)]):
    return UserResponse(
        id=str(current_user["_id"]),
        email=current_user["email"],
        role=resolve_user_role(current_user),
        balance=float(current_user.get("balance", 0.0)),
        createdAt=current_user.get("createdAt", utc_now_iso()),
    )
