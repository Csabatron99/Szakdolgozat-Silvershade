"""
Permission / authorization tests — §7.1

Covers:
- Admin-only endpoints reject regular users with 403
- Admin endpoints accept admin users
- Invalid ObjectId in URL path returns 400
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _FakeDatabase, auth_cookie, service_headers, _make_test_user


# ── Admin endpoint blocks regular users ──────────────────────────────────────

def test_admin_user_list_returns_403_for_regular_user(
    client: TestClient, test_user: dict
):
    resp = client.get("/api/v1/users", cookies=auth_cookie(test_user))
    assert resp.status_code == 403


def test_admin_user_list_returns_200_for_admin(
    client: TestClient, admin_user: dict, fake_db: _FakeDatabase
):
    resp = client.get("/api/v1/users", cookies=auth_cookie(admin_user))
    assert resp.status_code == 200


def test_change_user_role_returns_403_for_regular_user(
    client: TestClient, test_user: dict
):
    resp = client.patch(
        f"/api/v1/users/{test_user['id']}/role",
        json={"role": "admin"},
        cookies=auth_cookie(test_user),
    )
    assert resp.status_code == 403


def test_delete_user_returns_403_for_regular_user(
    client: TestClient, test_user: dict
):
    resp = client.delete(
        f"/api/v1/users/{test_user['id']}",
        cookies=auth_cookie(test_user),
    )
    assert resp.status_code == 403


# ── Service endpoints reject JWT auth ────────────────────────────────────────

def test_service_fivem_players_push_requires_service_key(
    client: TestClient, test_user: dict
):
    # JWT auth is not accepted on service endpoints
    resp = client.post(
        "/api/v1/service/fivem/players",
        json={"players": []},
        cookies=auth_cookie(test_user),
    )
    assert resp.status_code == 401


def test_service_fivem_players_get_requires_admin_jwt(
    client: TestClient, fake_db: _FakeDatabase
):
    # No auth at all
    resp = client.get("/api/v1/service/fivem/players")
    assert resp.status_code == 401


# ── Invalid ObjectId returns 400 ─────────────────────────────────────────────

def test_invalid_object_id_in_path_returns_400(
    client: TestClient, admin_user: dict
):
    resp = client.patch(
        "/api/v1/users/not-a-valid-objectid/role",
        json={"role": "user"},
        cookies=auth_cookie(admin_user),
    )
    assert resp.status_code == 400


def test_invalid_object_id_store_item_returns_400(
    client: TestClient, admin_user: dict
):
    resp = client.delete(
        "/api/v1/store/items/bad-id",
        cookies=auth_cookie(admin_user),
    )
    assert resp.status_code == 400


# ── DELETE endpoints return 204 with empty body ───────────────────────────────

def test_delete_own_account_returns_204(
    client: TestClient,
    fake_db: _FakeDatabase,
    test_user: dict,
):
    resp = client.delete("/api/v1/users/me", cookies=auth_cookie(test_user))
    assert resp.status_code == 204
    assert resp.content == b""


def test_admin_delete_user_returns_204(
    client: TestClient,
    fake_db: _FakeDatabase,
    admin_user: dict,
    test_user: dict,
):
    resp = client.delete(
        f"/api/v1/users/{test_user['id']}",
        cookies=auth_cookie(admin_user),
    )
    assert resp.status_code == 204
    assert resp.content == b""


# ── 422 on invalid request bodies ────────────────────────────────────────────

def test_buy_item_with_missing_field_returns_422(client: TestClient, test_user: dict):
    """FastAPI/Pydantic returns 422 when a required field is absent."""
    resp = client.post(
        "/api/v1/store/buy",
        json={},  # itemId is required
        cookies=auth_cookie(test_user),
    )
    assert resp.status_code == 422


def test_create_store_item_with_negative_price_returns_422(
    client: TestClient, admin_user: dict
):
    """Price must be > 0; negative value should be rejected by Pydantic."""
    resp = client.post(
        "/api/v1/store/items",
        json={"name": "Bad Item", "price": -5.0, "rewardData": {}},
        cookies=auth_cookie(admin_user),
    )
    assert resp.status_code == 422


def test_admin_action_with_oversized_reason_returns_422(
    client: TestClient, admin_user: dict
):
    """data.reason exceeding 500 chars should be rejected by the field validator."""
    resp = client.post(
        "/api/v1/admin-actions",
        json={
            "type": "kick",
            "playerId": "steam:1100001deadbeef",
            "data": {"reason": "x" * 501},
        },
        cookies=auth_cookie(admin_user),
    )
    assert resp.status_code == 422
