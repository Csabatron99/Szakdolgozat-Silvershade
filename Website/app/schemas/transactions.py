from pydantic import BaseModel, Field


class BuyItemRequest(BaseModel):
    itemId: str


class ConfirmTransactionRequest(BaseModel):
    transactionId: str
    status: str = Field(default="completed", pattern="^(pending|completed)$")


class CreateStoreItemRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    price: float = Field(gt=0)
    rewardData: dict
