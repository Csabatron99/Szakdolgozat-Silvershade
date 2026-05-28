from bson import ObjectId
from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import settings
from app.database.mongodb import get_database
from app.services.security import decode_access_token
from app.services.serializers import resolve_user_role

jwt_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(jwt_scheme),
    auth_cookie: str | None = Cookie(default=None, alias=settings.auth_cookie_name),
) -> dict:
    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif auth_cookie:
        token = auth_cookie

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing access token")

    payload = decode_access_token(token)
    database = get_database()
    user = await database.users.find_one({"_id": ObjectId(payload["sub"])})

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    user["role"] = resolve_user_role(user)

    return user


def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    if resolve_user_role(current_user) != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def validate_service_api_key(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

    try:
        scheme, token = authorization.split(" ", 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        ) from exc

    if scheme.lower() != "bearer" or token != settings.service_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return token
