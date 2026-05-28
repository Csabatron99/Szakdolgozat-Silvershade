from pydantic import BaseModel, Field

VALID_SCOPES: frozenset[str] = frozenset({"fivem", "discord"})


class CreateApiKeyRequest(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=100,
        description="Human-readable label for this key (e.g. 'FiveM Production', 'Discord Bot').",
    )
    scopes: list[str] = Field(
        default=["fivem", "discord"],
        description="Granted permission scopes. Valid values: `fivem`, `discord`.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {"name": "FiveM Server #1", "scopes": ["fivem"]}
        }
    }
