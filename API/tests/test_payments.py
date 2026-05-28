"""
Payment integration tests — §3

Covers:
- Creating a checkout session (mocked Stripe SDK)
- Webhook handling: checkout.session.completed marks transaction completed
- Webhook rejects invalid signature
- Payment status polling
- Refund (admin only) — mocked Stripe SDK
- Auth guards: unauthenticated users are blocked
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from tests.conftest import _FakeDatabase, _make_test_store_item, _make_test_user, auth_cookie


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_stripe_session(session_id: str = "cs_test_abc123", url: str = "https://checkout.stripe.com/pay/test") -> MagicMock:
    session = MagicMock()
    session.id = session_id
    session.url = url
    session.status = "complete"
    session.payment_status = "paid"
    session.amount_total = 1999
    session.currency = "usd"
    session.payment_intent = "pi_test_abc123"
    return session


def _fake_stripe_refund(refund_id: str = "re_test_xyz") -> MagicMock:
    refund = MagicMock()
    refund.id = refund_id
    refund.status = "succeeded"
    refund.amount = 1999
    refund.currency = "usd"
    return refund


def _build_webhook_payload(event_type: str, session_id: str) -> bytes:
    """Build a minimal Stripe webhook payload (no real signature — used when STRIPE_WEBHOOK_SECRET is empty)."""
    return json.dumps({
        "id": "evt_test",
        "type": event_type,
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "payment_status": "paid",
            }
        },
    }).encode()


# ── POST /api/v1/payments/create-checkout-session ────────────────────────────

def test_create_checkout_session_returns_201(
    client: TestClient,
    test_user: dict,
    test_store_item: dict,
    fake_db: _FakeDatabase,
):
    fake_session = _fake_stripe_session()

    with patch("app.routers.payments.stripe") as mock_stripe, \
         patch("app.routers.payments.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = ""
        mock_stripe.checkout.Session.create.return_value = fake_session
        mock_stripe.StripeError = Exception

        resp = client.post(
            "/api/v1/payments/create-checkout-session",
            json={"itemId": str(test_store_item["_id"])},
            cookies=auth_cookie(test_user),
        )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["sessionId"] == "cs_test_abc123"
    assert "checkout.stripe.com" in data["url"]


def test_create_checkout_session_requires_auth(client: TestClient, test_store_item: dict):
    resp = client.post(
        "/api/v1/payments/create-checkout-session",
        json={"itemId": str(test_store_item["_id"])},
    )
    assert resp.status_code == 401


def test_create_checkout_session_returns_404_for_unknown_item(
    client: TestClient, test_user: dict
):
    with patch("app.routers.payments.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = ""

        resp = client.post(
            "/api/v1/payments/create-checkout-session",
            json={"itemId": "0" * 24},
            cookies=auth_cookie(test_user),
        )

    assert resp.status_code == 404


def test_create_checkout_session_returns_503_when_stripe_not_configured(
    client: TestClient, test_user: dict, test_store_item: dict
):
    with patch("app.routers.payments.settings") as mock_settings:
        mock_settings.stripe_secret_key = ""

        resp = client.post(
            "/api/v1/payments/create-checkout-session",
            json={"itemId": str(test_store_item["_id"])},
            cookies=auth_cookie(test_user),
        )

    assert resp.status_code == 503


def test_create_checkout_session_returns_422_for_short_item_id(
    client: TestClient, test_user: dict
):
    resp = client.post(
        "/api/v1/payments/create-checkout-session",
        json={"itemId": "tooshort"},
        cookies=auth_cookie(test_user),
    )
    assert resp.status_code == 422


# ── POST /api/v1/payments/webhook ─────────────────────────────────────────────

def test_webhook_marks_transaction_completed(
    client: TestClient,
    fake_db: _FakeDatabase,
):
    """checkout.session.completed with payment_status=paid should flip the transaction to completed."""
    session_id = "cs_test_webhook_ok"
    item_id = ObjectId()
    user_id = ObjectId()

    # Pre-insert a pending transaction with the session ID.
    fake_db.transactions._docs.append({
        "_id": ObjectId(),
        "userId": user_id,
        "type": "stripe_checkout",
        "amount": 19.99,
        "status": "pending",
        "itemId": item_id,
        "stripeSessionId": session_id,
    })

    payload = json.dumps({
        "id": "evt_test",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "object": "checkout.session",
                "payment_status": "paid",
            }
        },
    }).encode()

    with patch("app.routers.payments.settings") as mock_settings, \
         patch("app.routers.payments.stripe") as mock_stripe:
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = ""   # skip signature check
        # Event.construct_from returns a dict-like object; use real payload parsing
        mock_stripe.Event.construct_from.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": session_id,
                    "payment_status": "paid",
                }
            },
        }
        mock_stripe.StripeError = Exception
        mock_stripe.SignatureVerificationError = Exception

        resp = client.post(
            "/api/v1/payments/webhook",
            content=payload,
            headers={"content-type": "application/json"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"received": True}

    # The transaction should now be completed in the fake DB.
    tx = next(
        (d for d in fake_db.transactions._docs if d.get("stripeSessionId") == session_id),
        None,
    )
    assert tx is not None
    assert tx["status"] == "completed"


def test_webhook_rejects_invalid_signature(client: TestClient):
    with patch("app.routers.payments.settings") as mock_settings, \
         patch("app.routers.payments.stripe") as mock_stripe:
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = "whsec_fake"

        class FakeSigError(Exception):
            pass

        mock_stripe.SignatureVerificationError = FakeSigError
        mock_stripe.Webhook.construct_event.side_effect = FakeSigError("bad sig")

        resp = client.post(
            "/api/v1/payments/webhook",
            content=b'{"type":"test"}',
            headers={"content-type": "application/json", "stripe-signature": "bad"},
        )

    assert resp.status_code == 400


# ── GET /api/v1/payments/{sessionId}/status ──────────────────────────────────

def test_get_payment_status_returns_session_data(
    client: TestClient, test_user: dict
):
    fake_session = _fake_stripe_session(session_id="cs_test_status")

    with patch("app.routers.payments.stripe") as mock_stripe, \
         patch("app.routers.payments.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = ""
        mock_stripe.checkout.Session.retrieve.return_value = fake_session
        mock_stripe.StripeError = Exception
        mock_stripe.InvalidRequestError = Exception

        resp = client.get(
            "/api/v1/payments/cs_test_status/status",
            cookies=auth_cookie(test_user),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["sessionId"] == "cs_test_status"
    assert data["status"] == "complete"
    assert data["paymentStatus"] == "paid"


def test_get_payment_status_requires_auth(client: TestClient):
    resp = client.get("/api/v1/payments/cs_test_abc/status")
    assert resp.status_code == 401


# ── POST /api/v1/payments/{transactionId}/refund ─────────────────────────────

def test_refund_returns_200_for_admin(
    client: TestClient,
    admin_user: dict,
    fake_db: _FakeDatabase,
):
    tx_id = ObjectId()
    fake_db.transactions._docs.append({
        "_id": tx_id,
        "status": "completed",
        "stripeSessionId": "cs_test_refund",
        "amount": 19.99,
    })

    fake_refund = _fake_stripe_refund()
    fake_session = _fake_stripe_session(session_id="cs_test_refund")

    with patch("app.routers.payments.stripe") as mock_stripe, \
         patch("app.routers.payments.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = ""
        mock_stripe.checkout.Session.retrieve.return_value = fake_session
        mock_stripe.Refund.create.return_value = fake_refund
        mock_stripe.StripeError = Exception
        mock_stripe.InvalidRequestError = Exception

        resp = client.post(
            f"/api/v1/payments/{tx_id}/refund",
            json={},
            cookies=auth_cookie(admin_user),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["refundId"] == "re_test_xyz"
    assert data["status"] == "succeeded"


def test_refund_returns_403_for_regular_user(
    client: TestClient,
    test_user: dict,
    fake_db: _FakeDatabase,
):
    tx_id = ObjectId()
    fake_db.transactions._docs.append({
        "_id": tx_id,
        "status": "completed",
        "stripeSessionId": "cs_test_refund2",
        "amount": 19.99,
    })

    with patch("app.routers.payments.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"

        resp = client.post(
            f"/api/v1/payments/{tx_id}/refund",
            json={},
            cookies=auth_cookie(test_user),
        )

    assert resp.status_code == 403


def test_refund_returns_409_for_pending_transaction(
    client: TestClient,
    admin_user: dict,
    fake_db: _FakeDatabase,
):
    tx_id = ObjectId()
    fake_db.transactions._docs.append({
        "_id": tx_id,
        "status": "pending",
        "stripeSessionId": "cs_test_cant_refund",
        "amount": 19.99,
    })

    with patch("app.routers.payments.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"

        resp = client.post(
            f"/api/v1/payments/{tx_id}/refund",
            json={},
            cookies=auth_cookie(admin_user),
        )

    assert resp.status_code == 409


def test_refund_returns_404_for_missing_transaction(
    client: TestClient, admin_user: dict
):
    with patch("app.routers.payments.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"

        resp = client.post(
            f"/api/v1/payments/{'0' * 24}/refund",
            json={},
            cookies=auth_cookie(admin_user),
        )

    assert resp.status_code == 404
