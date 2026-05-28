from pydantic import BaseModel, Field


class UpdateBalanceRequest(BaseModel):
    userId: str
    amount: float = Field(description="Positive or negative value to change user balance")


class UpdateBalanceResponse(BaseModel):
    userId: str
    balance: float
