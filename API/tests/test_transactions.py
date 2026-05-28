"""
Transaction flow tests — §7.1

Covers:
- Buy item success
- Buy item insufficient balance returns 400
- Confirm transaction marks it completed (PATCH /transactions/{id}/status)
- Transaction list is paginated
- DELETE store item returns 204
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from tests.conftest import (
    _FakeDatabase,
    _make_test_store_item,
    _make_test_user,
    auth_cookie,
    service_headers,
)


def _seed_transaction(fake_db: _FakeDatabase, user: dict, item: dict, status: str = "pending") -> dict:
    tid = ObjectId()
    tx = {
        "_id": tid,
        "id": str(tid),
        "userId": str(user["_id"]),
        "itemId": str(item["_id"]),
        "amount": item["price"],
        "status": status,
        "createdAt": datetime.now(UTC).isoformat(),
    }
    fake_db.transactions._docs.append(tx)
    return tx


# ── Buy item ──────────────────────────────────────────────────────────────────

def test_buy_item_success(
    client: TestClient,
    fake_db: _FakeDatabase,
    test_user: dict,
    test_store_item: dict,
):
    # Ensure user has enough balance
    test_user["balance"] = 100.0

    resp = client.post(
        "/api/v1/store/buy",
        json={"itemId": str(test_store_item["_id"])},
        cookies=auth_cookie(test_user),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["status"] == "pending"


def test_buy_item_insufficient_balance_returns_400(
    client: TestClient,
    fake_db: _FakeDatabase,
    test_user: dict,
    test_store_item: dict,
):
    test_user["balance"] = 0.0  # Not enough

    resp = client.post(
        "/api/v1/store/buy",
        json={"itemId": str(test_store_item["_id"])},
        cookies=auth_cookie(test_user),
    )
    assert resp.status_code == 400


def test_buy_item_nonexistent_returns_404(
    client: TestClient,
    fake_db: _FakeDatabase,
    test_user: dict,
):
    test_user["balance"] = 100.0
    fake_id = str(ObjectId())
    resp = client.post(
        "/api/v1/store/buy",
        json={"itemId": fake_id},
        cookies=auth_cookie(test_user),
    )
    assert resp.status_code == 404


# ── Confirm transaction ───────────────────────────────────────────────────────

def test_confirm_transaction_marks_completed(
    client: TestClient,
    fake_db: _FakeDatabase,
    test_user: dict,
    test_store_item: dict,
):
    tx = _seed_transaction(fake_db, test_user, test_store_item, status="pending")

    resp = client.patch(
        f"/api/v1/transactions/{tx['id']}/status",
        json={"status": "completed"},
        headers=service_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["status"] == "completed"


def test_confirm_transaction_invalid_id_returns_400(
    client: TestClient,
):
    resp = client.patch(
        "/api/v1/transactions/bad-id/status",
        json={"status": "completed"},
        headers=service_headers(),
    )
    assert resp.status_code == 400


# ── Transaction list pagination ───────────────────────────────────────────────

def test_transaction_list_includes_pagination_meta(
    client: TestClient,
    fake_db: _FakeDatabase,
    test_user: dict,
    test_store_item: dict,
):
    # Seed 3 transactions
    for _ in range(3):
        _seed_transaction(fake_db, test_user, test_store_item)

    resp = client.get(
        "/api/v1/transactions?page=1&limit=2",
        cookies=auth_cookie(test_user),
    )
    assert resp.status_code == 200
    meta = resp.json().get("meta", {})
    assert "total" in meta or "page" in meta  # paginate_response includes these


# ── Store item DELETE returns 204 ─────────────────────────────────────────────

def test_delete_store_item_returns_204(
    client: TestClient,
    fake_db: _FakeDatabase,
    admin_user: dict,
    test_store_item: dict,
):
    resp = client.delete(
        f"/api/v1/store/items/{test_store_item['id']}",
        cookies=auth_cookie(admin_user),
    )
    assert resp.status_code == 204
    assert resp.content == b""
