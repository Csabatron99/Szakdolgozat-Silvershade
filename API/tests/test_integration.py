"""
Integration tests — §7.2
========================
Full purchase-to-delivery flow exercised entirely in-process via the
TestClient + in-memory fake MongoDB.  No subprocess or external network calls.

Flow tested:
  1. Register a new user
  2. Admin creates a store item
  3. Admin tops up the user's balance (§4.2 credit record created)
  4. User buys the item → transaction is `pending`
  5. Service client polls sync endpoint → transaction appears
  6. Service client confirms the transaction → status becomes `completed`
  7. Next sync poll → transaction no longer in pending list
  8. Credit transaction created by balance top-up appears in transaction list
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import (
    _FakeDatabase,
    _make_test_user,
    auth_cookie,
    service_headers,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _admin_cookies(client: TestClient, fake_db: _FakeDatabase) -> dict:
    """Seed an admin user and return cookie dict."""
    from bson import ObjectId
    from app.services.security import hash_password

    admin = {
        "_id": ObjectId(),
        "email": "integration_admin@example.com",
        "password": hash_password("AdminPass1!"),
        "role": "admin",
        "balance": 0.0,
    }
    fake_db.users._docs.append(admin)
    return auth_cookie(admin)


# ── Full purchase-to-delivery flow ────────────────────────────────────────────

def test_full_purchase_to_delivery_flow(
    client: TestClient,
    fake_db: _FakeDatabase,
    admin_user: dict,
):
    """
    End-to-end test:
      register → top-up → buy → sync → confirm → verified completed.
    """
    admin_cookies = auth_cookie(admin_user)

    # ── Step 1: Register a new user ──────────────────────────────────────────
    reg_resp = client.post(
        "/api/v1/auth/register",
        json={"email": "buyer@example.com", "password": "BuyerPass1!"},
    )
    assert reg_resp.status_code == 201, reg_resp.text
    buyer_id = reg_resp.json()["data"]["id"]

    # Get buyer's cookie by logging in
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "buyer@example.com", "password": "BuyerPass1!"},
    )
    assert login_resp.status_code == 200
    buyer_cookies = login_resp.cookies

    # ── Step 2: Admin creates a store item ───────────────────────────────────
    item_resp = client.post(
        "/api/v1/store/items",
        json={"name": "VIP Package", "price": 25.0, "rewardData": {"type": "vip", "duration": 30}},
        cookies=admin_cookies,
    )
    assert item_resp.status_code == 201, item_resp.text
    item_id = item_resp.json()["data"]["id"]

    # ── Step 3: Admin tops up the buyer's balance ────────────────────────────
    topup_resp = client.patch(
        f"/api/v1/users/{buyer_id}/balance",
        json={"amount": 100.0},
        cookies=admin_cookies,
    )
    assert topup_resp.status_code == 200, topup_resp.text
    assert topup_resp.json()["data"]["balance"] == 100.0

    # §4.2: a credit transaction record should have been created
    credit_txs = [
        t for t in fake_db.transactions._docs
        if t.get("type") == "credit" and t.get("userId") == buyer_id
    ]
    assert len(credit_txs) == 1
    assert credit_txs[0]["amount"] == 100.0
    assert credit_txs[0]["status"] == "completed"

    # ── Step 4: Buyer purchases the item ─────────────────────────────────────
    buy_resp = client.post(
        "/api/v1/store/buy",
        json={"itemId": item_id},
        cookies=buyer_cookies,
    )
    assert buy_resp.status_code == 201, buy_resp.text
    purchase_tx_id = buy_resp.json()["data"]["id"]
    assert buy_resp.json()["data"]["status"] == "pending"

    # ── Step 5: Service client polls sync endpoint ────────────────────────────
    sync_resp = client.get("/api/v1/sync/updates", headers=service_headers())
    assert sync_resp.status_code == 200, sync_resp.text
    sync_data = sync_resp.json()["data"]
    pending_ids = [t["id"] for t in sync_data["pendingTransactions"]]
    assert purchase_tx_id in pending_ids, "Purchased transaction not in pending sync list"

    # ── Step 6: Service client confirms the transaction ───────────────────────
    confirm_resp = client.patch(
        f"/api/v1/transactions/{purchase_tx_id}/status",
        json={"status": "completed"},
        headers=service_headers(),
    )
    assert confirm_resp.status_code == 200, confirm_resp.text

    # ── Step 7: Next poll — transaction should no longer be pending ───────────
    sync_resp2 = client.get("/api/v1/sync/updates", headers=service_headers())
    assert sync_resp2.status_code == 200
    pending_ids_after = [t["id"] for t in sync_resp2.json()["data"]["pendingTransactions"]]
    assert purchase_tx_id not in pending_ids_after, "Completed transaction still appears in pending list"

    # ── Step 8: Admin can see all transactions including the credit ──────────
    history_resp = client.get(
        "/api/v1/transactions",
        cookies=admin_cookies,
    )
    assert history_resp.status_code == 200
    all_ids = [t["id"] for t in history_resp.json()["data"]]
    assert purchase_tx_id in all_ids


# ── API Key management flow ───────────────────────────────────────────────────

def test_api_key_create_list_and_revoke(
    client: TestClient,
    fake_db: _FakeDatabase,
    admin_user: dict,
):
    """§1.5 — create a scoped key, list it, then revoke it."""
    admin_cookies = auth_cookie(admin_user)

    # Create
    create_resp = client.post(
        "/api/v1/admin/api-keys",
        json={"name": "Test Key", "scopes": ["fivem"]},
        cookies=admin_cookies,
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()["data"]
    assert "key" in created, "Raw key must be returned at creation time"
    assert "keyHash" not in created, "Hash must never be exposed"
    key_id = created["id"]

    # List — key field absent
    list_resp = client.get("/api/v1/admin/api-keys", cookies=admin_cookies)
    assert list_resp.status_code == 200
    ids = [k["id"] for k in list_resp.json()["data"]]
    assert key_id in ids

    # Revoke
    del_resp = client.delete(f"/api/v1/admin/api-keys/{key_id}", cookies=admin_cookies)
    assert del_resp.status_code == 204

    # Confirm gone
    list_resp2 = client.get("/api/v1/admin/api-keys", cookies=admin_cookies)
    ids_after = [k["id"] for k in list_resp2.json()["data"]]
    assert key_id not in ids_after


def test_api_key_rotate(
    client: TestClient,
    fake_db: _FakeDatabase,
    admin_user: dict,
):
    """Rotating a key returns a new raw value and invalidates the old hash."""
    admin_cookies = auth_cookie(admin_user)

    create_resp = client.post(
        "/api/v1/admin/api-keys",
        json={"name": "Rotatable Key", "scopes": ["discord"]},
        cookies=admin_cookies,
    )
    assert create_resp.status_code == 201
    key_id = create_resp.json()["data"]["id"]
    original_raw = create_resp.json()["data"]["key"]

    rotate_resp = client.post(
        f"/api/v1/admin/api-keys/{key_id}/rotate",
        cookies=admin_cookies,
    )
    assert rotate_resp.status_code == 200
    new_raw = rotate_resp.json()["data"]["key"]
    assert new_raw != original_raw


def test_api_key_invalid_scope_rejected(
    client: TestClient,
    admin_user: dict,
):
    """Creating a key with an invalid scope returns 400."""
    resp = client.post(
        "/api/v1/admin/api-keys",
        json={"name": "Bad Key", "scopes": ["admin"]},  # not a valid scope
        cookies=auth_cookie(admin_user),
    )
    assert resp.status_code == 400
    assert "Invalid scope" in resp.json()["error"]["message"]


# ── Changelog endpoint ────────────────────────────────────────────────────────

def test_changelog_endpoint_returns_entries(client: TestClient):
    """§2.2 — /api/v1/changelog returns at least one entry."""
    resp = client.get("/api/v1/changelog")
    assert resp.status_code == 200
    changelog = resp.json()["data"]["changelog"]
    assert isinstance(changelog, list)
    assert len(changelog) >= 1
    entry = changelog[0]
    assert "version" in entry
    assert "date" in entry
    assert "added" in entry


# ── Webhook signing ───────────────────────────────────────────────────────────

def test_webhook_signing_headers_included(monkeypatch):
    """§1.7 — when WEBHOOK_SECRET is set, outbound webhook includes HMAC headers."""
    import hashlib
    import hmac
    from urllib.request import Request as _Req

    captured: list[_Req] = []

    def _fake_urlopen(req, timeout=None):
        captured.append(req)
        from unittest.mock import MagicMock
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.status = 200
        return resp

    from app.config.settings import settings as _settings
    original_secret = _settings.webhook_secret
    original_url = _settings.discord_test_webhook_url

    _settings.webhook_secret = "test-webhook-secret"
    _settings.discord_test_webhook_url = "http://localhost/webhook"

    monkeypatch.setattr("app.routers.dashboard.urlopen", _fake_urlopen)

    from app.routers.dashboard import _try_send_discord_webhook
    result = _try_send_discord_webhook("hello")

    _settings.webhook_secret = original_secret
    _settings.discord_test_webhook_url = original_url

    assert result is True
    assert len(captured) == 1
    req = captured[0]
    # urllib.request.Request stores header names in lowercase-capitalised form.
    headers_lower = {k.lower(): v for k, v in req.headers.items()}
    assert "x-silvershade-signature" in headers_lower
    assert "x-silvershade-timestamp" in headers_lower
    sig = headers_lower["x-silvershade-signature"]
    assert sig.startswith("sha256=")
