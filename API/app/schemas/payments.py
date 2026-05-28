from pydantic import BaseModel, Field


class CreateCheckoutSessionRequest(BaseModel):
    itemId: str = Field(
        min_length=24,
        max_length=24,
        description="MongoDB ObjectId of the store item to purchase",
    )

    model_config = {
        "json_schema_extra": {
            "example": {"itemId": "664a1b2c3d4e5f6a7b8c9d0e"}
        }
    }


class CheckoutSessionResponse(BaseModel):
    sessionId: str
    url: str


class PaymentStatusResponse(BaseModel):
    sessionId: str
    status: str
    paymentStatus: str | None = None
    amountTotal: int | None = None
    currency: str | None = None


class RefundRequest(BaseModel):
    reason: str = Field(
        default="requested_by_customer",
        max_length=200,
        description="Reason for the refund — stored on the Stripe refund object",
    )

    model_config = {
        "json_schema_extra": {
            "example": {"reason": "Customer requested refund"}
        }
    }


class RefundResponse(BaseModel):
    refundId: str
    status: str
    amount: int
    currency: str


class TopUpRequest(BaseModel):
    amount: float = Field(
        gt=0.50,
        le=10000,
        description="Amount in USD to top up (minimum $0.51, maximum $10,000)",
    )

    model_config = {
        "json_schema_extra": {
            "example": {"amount": 25.00}
        }
    }


class TopupPackageRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="Display name of the package")
    amount: float = Field(gt=0.50, le=10000, description="Amount in USD")
    description: str = Field(default="", max_length=200, description="Short description shown on the store")

    model_config = {
        "json_schema_extra": {
            "example": {"name": "Starter Pack", "amount": 10.00, "description": "Perfect for new players"}
        }
    }
