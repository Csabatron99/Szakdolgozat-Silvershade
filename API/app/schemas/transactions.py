from pydantic import BaseModel, Field


class BuyItemRequest(BaseModel):
    # MongoDB ObjectId is exactly 24 hex characters.
    itemId: str = Field(min_length=24, max_length=24, description="MongoDB ObjectId of the store item to purchase")

    model_config = {
        "json_schema_extra": {
            "example": {"itemId": "664a1b2c3d4e5f6a7b8c9d0e"}
        }
    }


class UpdateStoreItemRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100, description="Updated display name for the item")
    price: float | None = Field(default=None, gt=0, le=999_999, description="Updated price in USD")
    rewardData: dict | None = Field(default=None, description="Updated reward payload delivered to FiveM on purchase")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "VIP Package (Updated)",
                "price": 24.99,
            }
        }
    }


class CreateStoreItemRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100, description="Display name shown in the store")
    price: float = Field(gt=0, le=999_999, description="Price in USD")
    rewardData: dict = Field(description="Reward payload sent to FiveM when this item is purchased (e.g. `{\"type\": \"money\", \"amount\": 1000}`)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "VIP Package",
                "price": 19.99,
                "rewardData": {"type": "vip", "duration": 30},
            }
        }
    }
