from pydantic import BaseModel, Field


class BalanceAdjustRequest(BaseModel):
    amount: float = Field(
        description="Amount to add (positive) or subtract (negative) from user balance",
        ge=-999_999,
        le=999_999,
    )

    model_config = {
        "json_schema_extra": {
            "example": {"amount": 50.0}
        }
    }


class UpdateBalanceResponse(BaseModel):
    userId: str
    balance: float


class ChangePasswordRequest(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=128)
    newPassword: str = Field(min_length=8, max_length=128)

    model_config = {
        "json_schema_extra": {
            "example": {"currentPassword": "<current>", "newPassword": "<new-min-8-chars>"}
        }
    }


class RoleUpdateRequest(BaseModel):
    role: str = Field(pattern="^(user|admin)$")

    model_config = {
        "json_schema_extra": {
            "example": {"role": "admin"}
        }
    }


class LinkedAccountsRequest(BaseModel):
    discordId: str | None = Field(default=None, max_length=64, description="Discord user ID or username")
    fivemId: str | None = Field(default=None, max_length=64, description="FiveM player identifier")

    model_config = {
        "json_schema_extra": {
            "example": {"discordId": "123456789012345678", "fivemId": "steam:1100001abcdef01"}
        }
    }
