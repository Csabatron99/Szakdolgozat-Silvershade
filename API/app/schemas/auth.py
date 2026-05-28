from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr = Field(max_length=254, description="User's email address (used as login username)")
    password: str = Field(min_length=8, max_length=128, description="Password — minimum 8 characters")

    model_config = {
        "json_schema_extra": {
            "example": {"email": "player@example.com", "password": "SecurePass123"}
        }
    }


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=254, description="Registered email address")
    password: str = Field(min_length=8, max_length=128, description="Account password")

    model_config = {
        "json_schema_extra": {
            "example": {"email": "player@example.com", "password": "SecurePass123"}
        }
    }


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    role: str
    balance: float
    createdAt: str
    discordId: str | None = None
    fivemId: str | None = None
