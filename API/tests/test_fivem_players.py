"""
FiveM players panel tests — §4.1 / §7.1

Covers:
- Service key can push player list → 200
- Admin JWT can read player snapshot → 200
- Empty state returns empty list
- Invalid data returns 400
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _FakeDatabase, admin_user, auth_cookie, service_headers


def test_push_players_success(client: TestClient, fake_db: _FakeDatabase):
    players = [
        {"id": "p1", "name": "Alex", "money": 1200, "roles": ["player"], "banned": False},
        {"id": "p2", "name": "Jordan", "money": 550, "roles": ["player", "vip"], "banned": False},
    ]
    resp = client.post(
        "/api/v1/service/fivem/players",
        json={"players": players},
        headers=service_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["pushed"] == 2


def test_push_players_invalid_payload_returns_400(client: TestClient):
    resp = client.post(
        "/api/v1/service/fivem/players",
        json={"players": "not-a-list"},
        headers=service_headers(),
    )
    assert resp.status_code == 400


def test_get_players_empty_state(
    client: TestClient, fake_db: _FakeDatabase, admin_user: dict
):
    resp = client.get(
        "/api/v1/service/fivem/players",
        cookies=auth_cookie(admin_user),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"]["players"] == []


def test_get_players_returns_pushed_state(
    client: TestClient, fake_db: _FakeDatabase, admin_user: dict
):
    players = [{"id": "p1", "name": "Alex", "money": 1200, "roles": ["player"], "banned": False}]
    client.post(
        "/api/v1/service/fivem/players",
        json={"players": players},
        headers=service_headers(),
    )
    resp = client.get(
        "/api/v1/service/fivem/players",
        cookies=auth_cookie(admin_user),
    )
    assert resp.status_code == 200
    returned = resp.json()["data"]["players"]
    assert len(returned) == 1
    assert returned[0]["name"] == "Alex"


def test_get_players_requires_admin(
    client: TestClient, fake_db: _FakeDatabase, test_user: dict
):
    resp = client.get(
        "/api/v1/service/fivem/players",
        cookies=auth_cookie(test_user),
    )
    assert resp.status_code == 403
