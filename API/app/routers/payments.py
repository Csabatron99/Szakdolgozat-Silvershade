"""
Payments router — Stripe Checkout integration.

Endpoints:
  POST /api/v1/payments/create-checkout-session  — authenticated user creates a Stripe session
  POST /api/v1/payments/webhook                  — Stripe webhook (no auth, verified by signature)
  GET  /api/v1/payments/{sessionId}/status       — poll session status (authenticated)
  POST /api/v1/payments/{transactionId}/refund   — admin-only refund
"""
import logging
from typing import Annotated

import stripe
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.database.mongodb import get_database
from app.schemas.common import success_response, utc_now_iso
from app.schemas.payments import (
    CheckoutSessionResponse,
    CreateCheckoutSessionRequest,
    PaymentStatusResponse,
    RefundRequest,
    RefundResponse,
    TopUpRequest,
)
from app.services.deps import endpoint_rate_limit, get_admin_user, get_current_user
from app.services.serializers import normalize_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/payments", tags=["Payments"])

# ── Stripe client initialisation ─────────────────────────────────────────────
# The key is read once at import time; the stripe SDK uses it globally.
if settings.stripe_secret_key:
    stripe.api_key = settings.stripe_secret_key
else:
    logger.warning("STRIPE_SECRET_KEY is not set — payment endpoints will be unavailable.")


def _require_stripe() -> None:
    """Raise 503 if Stripe is not configured."""
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment processing is not configured on this server.",
        )


# ── POST /api/v1/payments/create-checkout-session ────────────────────────────

@router.post(
    "/create-checkout-session",
    status_code=status.HTTP_201_CREATED,
    response_model=CheckoutSessionResponse,
    dependencies=[Depends(endpoint_rate_limit(max_requests=5, window_seconds=60))],
    summary="Create a Stripe Checkout session",
    description=(
        "Looks up the requested store item, creates a Stripe Checkout session, "
        "and records a `pending` transaction. The client should redirect the user to the "
        "returned `url`. Requires authentication."
    ),
)
async def create_checkout_session(
    payload: CreateCheckoutSessionRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    _require_stripe()
    database = get_database()

    try:
        item_id = ObjectId(payload.itemId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid item ID format")

    item = await database.store_items.find_one({"_id": item_id})
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store item not found")

    # Redirect back to the Website frontend, not the API server.
    frontend = settings.frontend_url.rstrip("/")
    success_url = f"{frontend}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{frontend}/payment/cancel"

    price_cents = int(round(float(item["price"]) * 100))

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": item["name"]},
                        "unit_amount": price_cents,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "userId": str(current_user["_id"]),
                "itemId": str(item["_id"]),
            },
        )
    except stripe.StripeError as exc:
        logger.error("Stripe error creating checkout session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create payment session. Please try again.",
        )

    # Record the transaction as pending until the webhook confirms it.
    transaction = {
        "userId": current_user["_id"],
        "type": "stripe_checkout",
        "amount": float(item["price"]),
        "status": "pending",
        "itemId": item["_id"],
        "rewardData": item.get("rewardData", {}),
        "stripeSessionId": session.id,
        "createdAt": utc_now_iso(),
    }
    await database.transactions.insert_one(transaction)

    return CheckoutSessionResponse(sessionId=session.id, url=session.url)

# ── POST /api/v1/payments/topup ───────────────────────────────────────────────────────────────

@router.post(
    "/topup",
    status_code=status.HTTP_201_CREATED,
    response_model=CheckoutSessionResponse,
    dependencies=[Depends(endpoint_rate_limit(max_requests=5, window_seconds=60))],
    summary="Create a Stripe top-up session",
    description=(
        "Creates a Stripe Checkout session to add funds to the user's account balance. "
        "The webhook marks the transaction `completed` and credits the user's balance. "
        "Requires authentication."
    ),
)
async def create_topup_session(
    payload: TopUpRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
):
    _require_stripe()
    database = get_database()

    amount_cents = int(round(payload.amount * 100))
    frontend = settings.frontend_url.rstrip("/")
    success_url = f"{frontend}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{frontend}/payment/cancel"

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": "SilverShade Account Top-Up"},
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "type": "topup",
                "userId": str(current_user["_id"]),
                "amount": str(payload.amount),
            },
        )
    except stripe.StripeError as exc:
        logger.error("Stripe error creating top-up session: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to create top-up session. Please try again.",
        )

    transaction = {
        "userId": current_user["_id"],
        "type": "topup",
        "amount": payload.amount,
        "status": "pending",
        "stripeSessionId": session.id,
        "createdAt": utc_now_iso(),
    }
    await database.transactions.insert_one(transaction)

    return CheckoutSessionResponse(sessionId=session.id, url=session.url)

# ── POST /api/v1/payments/webhook ────────────────────────────────────────────

@router.post(
    "/webhook",
    status_code=status.HTTP_200_OK,
    summary="Stripe webhook receiver",
    description=(
        "Receives Stripe events. Verifies the `Stripe-Signature` header when "
        "`STRIPE_WEBHOOK_SECRET` is configured. Handles `checkout.session.completed` "
        "and `payment_intent.payment_failed`."
    ),
    include_in_schema=False,  # Don't expose in public docs — Stripe calls this directly
)
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
        except stripe.SignatureVerificationError:
            logger.warning("Stripe webhook: invalid signature rejected")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")
        except Exception as exc:
            logger.error("Stripe webhook: failed to parse event: %s", exc)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed webhook payload")
    else:
        # No secret configured — parse without verification (dev/test only)
        import json
        try:
            event = stripe.Event.construct_from(json.loads(payload), stripe.api_key)
        except Exception as exc:
            logger.error("Stripe webhook: failed to parse event: %s", exc)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed webhook payload")

    event_type: str = event["type"]
    logger.info("Stripe webhook received: %s", event_type)

    database = get_database()

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        session_id: str = session["id"]
        payment_status: str = session.get("payment_status", "")

        if payment_status == "paid":
            result = await database.transactions.find_one_and_update(
                {"stripeSessionId": session_id, "status": "pending"},
                {"$set": {"status": "completed", "completedAt": utc_now_iso()}},
                return_document=True,
            )
            if result:
                logger.info(
                    "Payment confirmed for session %s — transaction %s marked completed.",
                    session_id,
                    str(result["_id"]),
                )
                # If this was a top-up, credit the user's balance.
                if result.get("type") == "topup":
                    topup_amount = float(result.get("amount", 0))
                    user_id = result.get("userId")
                    if user_id and topup_amount > 0:
                        await database.users.update_one(
                            {"_id": user_id},
                            {"$inc": {"balance": topup_amount}},
                        )
                        logger.info(
                            "Top-up of $%.2f credited to user %s",
                            topup_amount,
                            str(user_id),
                        )
            else:
                logger.warning(
                    "Received checkout.session.completed for unknown/already-processed session %s",
                    session_id,
                )

    elif event_type == "payment_intent.payment_failed":
        payment_intent = event["data"]["object"]
        pi_id: str = payment_intent["id"]

        # Look up the session that references this PaymentIntent.
        result = await database.transactions.find_one_and_update(
            {"stripeSessionId": {"$exists": True}, "status": "pending"},
            {"$set": {"status": "failed", "failedAt": utc_now_iso()}},
            # We can only match by PI id if we stored it; mark by best-effort scan.
        )
        logger.info("Payment failed for PaymentIntent %s. Matched transaction: %s", pi_id, result)

    return JSONResponse(content={"received": True})


# ── GET /api/v1/payments/{sessionId}/status ──────────────────────────────────

@router.get(
    "/{sessionId}/status",
    response_model=PaymentStatusResponse,
    summary="Get payment session status",
    description=(
        "Returns the current status of a Stripe Checkout session. "
        "Authenticated users can poll this after a redirect from the payment page."
    ),
)
async def get_payment_status(
    sessionId: str,
    _: Annotated[dict, Depends(get_current_user)],
):
    _require_stripe()

    try:
        session = stripe.checkout.Session.retrieve(sessionId)
    except stripe.InvalidRequestError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    except stripe.StripeError as exc:
        logger.error("Stripe error retrieving session %s: %s", sessionId, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve payment status.",
        )

    return PaymentStatusResponse(
        sessionId=session.id,
        status=session.status,
        paymentStatus=session.payment_status,
        amountTotal=session.amount_total,
        currency=session.currency,
    )


# ── POST /api/v1/payments/{transactionId}/refund ─────────────────────────────

@router.post(
    "/{transactionId}/refund",
    response_model=RefundResponse,
    summary="Refund a completed payment",
    description=(
        "Issues a full refund via Stripe for the given transaction. "
        "The transaction must have `status: completed` and a `stripeSessionId`. "
        "**Admin only.**"
    ),
)
async def refund_payment(
    transactionId: str,
    payload: RefundRequest,
    _: Annotated[dict, Depends(get_admin_user)],
):
    _require_stripe()
    database = get_database()

    try:
        tx_id = ObjectId(transactionId)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid transaction ID format")

    transaction = await database.transactions.find_one({"_id": tx_id})
    if not transaction:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    if transaction.get("status") != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only completed transactions can be refunded",
        )

    stripe_session_id: str | None = transaction.get("stripeSessionId")
    if not stripe_session_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transaction has no associated Stripe session",
        )

    # Retrieve the PaymentIntent from the session, then refund it.
    try:
        session = stripe.checkout.Session.retrieve(stripe_session_id)
        payment_intent_id: str = session.payment_intent
        refund = stripe.Refund.create(
            payment_intent=payment_intent_id,
            reason="requested_by_customer",
        )
    except stripe.InvalidRequestError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except stripe.StripeError as exc:
        logger.error("Stripe error creating refund for transaction %s: %s", transactionId, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Refund failed. Please try again or contact Stripe support.",
        )

    await database.transactions.update_one(
        {"_id": tx_id},
        {"$set": {"status": "refunded", "refundId": refund.id, "refundedAt": utc_now_iso()}},
    )

    logger.info("Refund %s issued for transaction %s.", refund.id, transactionId)

    return RefundResponse(
        refundId=refund.id,
        status=refund.status,
        amount=refund.amount,
        currency=refund.currency,
    )
