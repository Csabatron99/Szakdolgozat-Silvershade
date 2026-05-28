from pydantic import BaseModel, Field, field_validator

_MAX_DATA_STR_LEN = 500


class CreateAdminActionRequest(BaseModel):
    type: str = Field(pattern="^(ban|kick|give_role|remove_role)$", description="Action type: `ban`, `kick`, `give_role`, or `remove_role`")
    playerId: str = Field(min_length=1, max_length=128, description="FiveM player identifier (e.g. `steam:1100001deadbeef`)")
    data: dict = Field(description="Action parameters — `reason` for bans/kicks, `role` for role changes")

    @field_validator("data")
    @classmethod
    def _validate_data_strings(cls, v: dict) -> dict:
        """Ensure no string value inside data exceeds 500 characters."""
        for key, val in v.items():
            if isinstance(val, str) and len(val) > _MAX_DATA_STR_LEN:
                raise ValueError(f"data.{key} must be at most {_MAX_DATA_STR_LEN} characters")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "type": "ban",
                "playerId": "steam:1100001deadbeef",
                "data": {"reason": "Cheating", "duration": "permanent"},
            }
        }
    }
