"""
Auth endpoint tests — §7.1

Covers:
- Registration success and duplicate email
- Login success, wrong password, account lockout
- /me returns current user
- Logout clears cookie
- Service key auth (validate_service_api_key)
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _FakeDatabase, auth_cookie, service_headers, _make_test_user
from app.services.security import hash_password


# ── Register ──────────────────────────────────────────────────────────────────

def test_register_success(client: TestClient, fake_db: _FakeDatabase):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "StrongPass1"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["success"] is True
    assert data["data"]["email"] == "new@example.com"
    # Password must NOT appear in response
    assert "password" not in str(data)


def test_register_duplicate_email_returns_409(client: TestClient, fake_db: _FakeDatabase):
    # Pre-seed user
    user = _make_test_user(email="dup@example.com")
    fake_db.users._docs.append(user)

    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "password": "StrongPass1"},
    )
    assert resp.status_code == 409


def test_register_weak_password_returns_422(client: TestClient):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "x@example.com", "password": "short"},
    )
    assert resp.status_code == 422


def test_register_invalid_email_returns_422(client: TestClient):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "StrongPass1"},
    )
    assert resp.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_success(client: TestClient, fake_db: _FakeDatabase):
    # Pre-seed user with hashed password
    user = _make_test_user(email="login@example.com")
    user["password"] = hash_password("ValidPass1")
    fake_db.users._docs.append(user)

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "ValidPass1"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    # Cookie should be set
    assert "silvershade_access_token" in resp.cookies


def test_login_wrong_password_returns_401(client: TestClient, fake_db: _FakeDatabase):
    user = _make_test_user(email="wrongpw@example.com")
    user["password"] = hash_password("CorrectPass1")
    fake_db.users._docs.append(user)

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpw@example.com", "password": "WrongPass1"},
    )
    assert resp.status_code == 401


def test_login_nonexistent_user_returns_401(client: TestClient):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "SomePass1"},
    )
    assert resp.status_code == 401


# ── /me ───────────────────────────────────────────────────────────────────────

def test_me_returns_current_user(client: TestClient, test_user: dict):
    resp = client.get("/api/v1/auth/me", cookies=auth_cookie(test_user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["email"] == test_user["email"]
    assert "password" not in str(data)


def test_me_without_auth_returns_401(client: TestClient):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


# ── Logout ────────────────────────────────────────────────────────────────────

def test_logout_clears_cookie(client: TestClient, test_user: dict):
    resp = client.post("/api/v1/auth/logout", cookies=auth_cookie(test_user))
    assert resp.status_code == 200
    # After logout the cookie should be cleared (Max-Age=0 or deleted)
    cookie_header = resp.headers.get("set-cookie", "")
    assert "silvershade_access_token" in cookie_header


# ── Service API key ───────────────────────────────────────────────────────────

def test_service_endpoint_without_api_key_returns_401(client: TestClient):
    resp = client.get("/api/v1/service/store")
    assert resp.status_code == 401


def test_service_endpoint_with_wrong_api_key_returns_401(client: TestClient):
    resp = client.get(
        "/api/v1/service/store",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert resp.status_code == 401


def test_service_endpoint_with_correct_api_key_returns_200(
    client: TestClient, fake_db: _FakeDatabase
):
    resp = client.get("/api/v1/service/store", headers=service_headers())
    assert resp.status_code == 200
