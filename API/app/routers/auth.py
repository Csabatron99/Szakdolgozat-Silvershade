from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import settings
from app.database.mongodb import get_database
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.schemas.common import success_response, utc_now_iso
from app.services.deps import endpoint_rate_limit, get_current_user
from app.services.security import create_access_token, decode_access_token, hash_password, verify_password
from app.services.serializers import resolve_user_role

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

_jwt_scheme = HTTPBearer(auto_error=False)

# Account lockout: lock after this many consecutive failures, for this many minutes.
_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


async def _check_and_record_failed_login(database, user: dict) -> None:
    """Increment failed attempt counter; lock account if threshold reached."""
    attempts = user.get("failed_login_attempts", 0) + 1
    update: dict = {"$set": {"failed_login_attempts": attempts}}
    if attempts >= _MAX_FAILED_ATTEMPTS:
        from datetime import timedelta
        locked_until = datetime.now(timezone.utc) + timedelta(minutes=_LOCKOUT_MINUTES)
        update["$set"]["login_locked_until"] = locked_until.isoformat()
    await database.users.update_one({"_id": user["_id"]}, update)


async def _verify_and_normalize_password(database, user: dict, plain_password: str) -> bool:
    stored_password = user.get("password") or user.get("password_hash") or ""
    if not isinstance(stored_password, str) or not stored_password:
        return False

    # All passwords in the database must be bcrypt hashes by this point.
    # The startup migration in main.py ensures any remaining plaintext passwords
    # are hashed before requests are served.
    try:
        return verify_password(plain_password, stored_password)
    except Exception:
        return False


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Creates a new user account. Returns the created user profile. Rate-limited to 5 requests/minute per IP.",
)
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
    return success_response(UserResponse(
        id=str(result.inserted_id),
        email=document["email"],
        role=document["role"],
        balance=document["balance"],
        createdAt=document["createdAt"],
    ).model_dump())


@router.post(
    "/login",
    summary="Log in",
    description="Authenticates a user and sets an `httpOnly` JWT cookie. Rate-limited to 10 requests/minute per IP. Returns `429` when the account is locked after too many failed attempts.",
)
async def login(payload: LoginRequest, response: Response):
    database = get_database()
    user = await database.users.find_one({"email": payload.email.lower()})

    # Use the same vague error for "user not found" and "wrong password" to
    # prevent username enumeration attacks.
    _invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user:
        raise _invalid

    # Check account lockout.
    locked_until_raw = user.get("login_locked_until")
    if locked_until_raw:
        locked_until = datetime.fromisoformat(locked_until_raw)
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < locked_until:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account locked due to too many failed attempts. Try again in {_LOCKOUT_MINUTES} minutes.",
                headers={"Retry-After": str(_LOCKOUT_MINUTES * 60)},
            )

    password_valid = await _verify_and_normalize_password(database, user, payload.password)

    if not password_valid:
        await _check_and_record_failed_login(database, user)
        raise _invalid

    role = resolve_user_role(user)

    # Successful login — reset lockout counters.
    await database.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "role": role,
                "balance": float(user.get("balance", 0.0)),
                "createdAt": user.get("createdAt", utc_now_iso()),
                "failed_login_attempts": 0,
                "login_locked_until": None,
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
    return success_response({"access_token": token, "token_type": "bearer"})


@router.post(
    "/refresh",
    summary="Refresh access token",
    description="Issues a new JWT if the current token is still valid (sliding session). Accepts the token via cookie or `Authorization: Bearer` header.",
)
async def refresh_token(
    response: Response,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_jwt_scheme)] = None,
    auth_cookie: Annotated[str | None, Cookie(alias=settings.auth_cookie_name)] = None,
):
    """Issue a new token if the current one is still valid (sliding session)."""
    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif auth_cookie:
        token = auth_cookie

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")

    payload = decode_access_token(token)

    database = get_database()
    from bson import ObjectId
    user = await database.users.find_one({"_id": ObjectId(payload["sub"])})
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    role = resolve_user_role(user)
    new_token = create_access_token(subject=str(user["_id"]), role=role)
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=new_token,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        max_age=settings.access_token_expire_minutes * 60,
    )
    return success_response({"access_token": new_token, "token_type": "bearer"})


@router.post(
    "/logout",
    summary="Log out",
    description="Clears the JWT cookie. Always returns `200` regardless of whether the user was logged in.",
)
async def logout(response: Response):
    response.delete_cookie(key=settings.auth_cookie_name, httponly=True, samesite="lax")
    return success_response({"message": "Logged out"})


@router.get(
    "/me",
    summary="Get current user",
    description="Returns the profile of the currently authenticated user based on the JWT cookie.",
)
async def get_me(current_user: Annotated[dict, Depends(get_current_user)]):
    return success_response(UserResponse(
        id=str(current_user["_id"]),
        email=current_user["email"],
        role=resolve_user_role(current_user),
        balance=float(current_user.get("balance", 0.0)),
        createdAt=current_user.get("createdAt", utc_now_iso()),
        discordId=current_user.get("discordId") or None,
        fivemId=current_user.get("fivemId") or None,
    ).model_dump())
