"""
Test fixtures shared across all test modules.

Strategy
--------
- The FastAPI app is imported *after* patching `settings` so the startup
  secret-strength check always passes in tests.
- MongoDB is replaced with an in-memory `mongomock_motor` client via
  `app.database.mongodb.get_database` dependency override.  We use a simple
  `MagicMock` dict-based stub so we don't need an extra test dependency.
- All auth tokens are created with the test SECRET_KEY so they are valid.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from jose import jwt

# ── Force safe settings before importing `main` ──────────────────────────────
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-32chars")
os.environ.setdefault("SERVICE_API_KEY", "test-service-api-key")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("ALLOWED_ORIGINS", "http://testserver")

# ── Patch _validate_secrets so app starts without a real .env ────────────────
with patch("app.config.settings.Settings.model_post_init", lambda self, *a, **k: None):
    pass  # settings already loaded; just ensure env vars are picked up


def _make_test_user(
    *,
    email: str = "test@example.com",
    role: str = "user",
    balance: float = 100.0,
) -> dict:
    uid = ObjectId()
    return {
        "_id": uid,
        "id": str(uid),
        "email": email,
        "password": "$2b$12$placeholder",  # won't be checked in most tests
        "role": role,
        "balance": balance,
        "createdAt": datetime.now(UTC).isoformat(),
        "updatedAt": datetime.now(UTC).isoformat(),
    }


def _make_test_store_item(
    *,
    name: str = "VIP Package",
    price: float = 19.99,
) -> dict:
    iid = ObjectId()
    return {
        "_id": iid,
        "id": str(iid),
        "name": name,
        "price": price,
        "rewardData": {"type": "vip", "duration": 30},
        "createdAt": datetime.now(UTC).isoformat(),
    }


def _create_token(user: dict, secret: str = "test-secret-key-that-is-long-enough-32chars") -> str:
    payload = {
        "sub": str(user["_id"]),
        "role": user["role"],
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


# ── In-memory database stub ───────────────────────────────────────────────────

class _FakeCollection:
    """Minimal async MongoDB collection stub backed by a plain list."""

    def __init__(self) -> None:
        self._docs: list[dict] = []

    def _match(self, doc: dict, query: dict) -> bool:
        for k, v in query.items():
            if k == "_id":
                if doc.get("_id") != v:
                    return False
            elif isinstance(v, dict):
                # Simple operator support: $exists
                if "$exists" in v:
                    has_key = k in doc
                    if v["$exists"] and not has_key:
                        return False
                    if not v["$exists"] and has_key:
                        return False
            elif doc.get(k) != v:
                return False
        return True

    async def find_one(self, query: dict, projection: dict | None = None) -> dict | None:
        for doc in self._docs:
            if self._match(doc, query):
                return dict(doc)
        return None

    def find(self, query: dict | None = None, projection: dict | None = None) -> "_FakeCursor":
        return _FakeCursor(self._docs, query or {})

    async def insert_one(self, doc: dict):
        # Mimic real MongoDB: assign _id in-place if not already present.
        if "_id" not in doc:
            doc["_id"] = ObjectId()
        self._docs.append(dict(doc))
        result = MagicMock()
        result.inserted_id = doc["_id"]
        return result

    async def update_one(self, query: dict, update: dict, upsert: bool = False):
        for doc in self._docs:
            if self._match(doc, query):
                if "$set" in update:
                    doc.update(update["$set"])
                result = MagicMock()
                result.matched_count = 1
                result.modified_count = 1
                return result
        if upsert:
            new_doc = {**query, **update.get("$set", {})}
            self._docs.append(new_doc)
        result = MagicMock()
        result.matched_count = 0
        result.modified_count = 0
        return result

    async def replace_one(self, query: dict, replacement: dict, upsert: bool = False):
        for i, doc in enumerate(self._docs):
            if self._match(doc, query):
                self._docs[i] = dict(replacement)
                result = MagicMock()
                result.matched_count = 1
                return result
        if upsert:
            self._docs.append(dict(replacement))
        result = MagicMock()
        result.matched_count = 0
        return result

    async def delete_one(self, query: dict):
        for i, doc in enumerate(self._docs):
            if self._match(doc, query):
                self._docs.pop(i)
                result = MagicMock()
                result.deleted_count = 1
                return result
        result = MagicMock()
        result.deleted_count = 0
        return result

    async def find_one_and_update(
        self,
        query: dict,
        update: dict,
        return_document: bool = False,
        upsert: bool = False,
    ) -> dict | None:
        """Mimics Motor's find_one_and_update. return_document=True returns post-update doc."""
        for doc in self._docs:
            if self._match(doc, query):
                if return_document:
                    # Apply update then return the new state
                    if "$set" in update:
                        doc.update(update["$set"])
                    return dict(doc)
                else:
                    before = dict(doc)
                    if "$set" in update:
                        doc.update(update["$set"])
                    return before
        return None

    async def count_documents(self, query: dict) -> int:
        return sum(1 for d in self._docs if self._match(d, query))

    async def create_index(self, *args, **kwargs):
        return None


class _FakeCursor:
    def __init__(self, docs: list[dict], query: dict) -> None:
        self._docs = [d for d in docs if self._match(d, query)]
        self._skip_n = 0
        self._limit_n = 0

    @staticmethod
    def _match(doc: dict, query: dict) -> bool:
        for k, v in query.items():
            if isinstance(v, dict):
                if "$exists" in v:
                    has_key = k in doc
                    if v["$exists"] and not has_key:
                        return False
            elif doc.get(k) != v:
                return False
        return True

    def skip(self, n: int) -> "_FakeCursor":
        self._skip_n = n
        return self

    def limit(self, n: int) -> "_FakeCursor":
        self._limit_n = n
        return self

    def sort(self, *args, **kwargs) -> "_FakeCursor":
        return self

    async def to_list(self, length: int | None = None) -> list[dict]:
        docs = self._docs[self._skip_n:]
        if self._limit_n:
            docs = docs[: self._limit_n]
        if length is not None:
            docs = docs[:length]
        return [dict(d) for d in docs]

    def __aiter__(self):
        return self

    async def __anext__(self):
        docs = self._docs[self._skip_n:]
        if self._limit_n:
            docs = docs[: self._limit_n]
        if not docs:
            raise StopAsyncIteration
        self._skip_n += 1
        return dict(docs[0])


class _FakeDatabase:
    def __init__(self) -> None:
        self.users = _FakeCollection()
        self.transactions = _FakeCollection()
        self.store_items = _FakeCollection()
        self.admin_actions = _FakeCollection()
        self.idempotency_cache = _FakeCollection()
        self.fivem_state = _FakeCollection()

    def __getattr__(self, name: str) -> _FakeCollection:
        col = _FakeCollection()
        setattr(self, name, col)
        return col


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_db() -> _FakeDatabase:
    return _FakeDatabase()


@pytest.fixture()
def test_user(fake_db: _FakeDatabase) -> dict:
    user = _make_test_user()
    fake_db.users._docs.append(user)
    return user


@pytest.fixture()
def admin_user(fake_db: _FakeDatabase) -> dict:
    user = _make_test_user(email="admin@example.com", role="admin", balance=0.0)
    fake_db.users._docs.append(user)
    return user


@pytest.fixture()
def test_store_item(fake_db: _FakeDatabase) -> dict:
    item = _make_test_store_item()
    fake_db.store_items._docs.append(item)
    return item


@pytest.fixture()
def client(fake_db: _FakeDatabase) -> TestClient:
    """Return a TestClient with MongoDB replaced by the in-memory fake."""
    from app.config.settings import settings as _settings

    # Override settings so tokens + service key match test values.
    _TEST_SECRET = "test-secret-key-that-is-long-enough-32chars"
    _TEST_SVC_KEY = "test-service-api-key"
    original_secret = _settings.secret_key
    original_svc_key = _settings.service_api_key
    _settings.secret_key = _TEST_SECRET
    _settings.service_api_key = _TEST_SVC_KEY

    import main as _main
    import app.database.mongodb as _mongo_mod

    # We patch connect_to_mongo to be a no-op AND pre-set _database to fake_db.
    # The startup event calls connect_to_mongo() then get_database(); by making
    # connect_to_mongo a no-op and pre-seeding _database, the startup event reads
    # our fake DB and all request handlers use it throughout.
    original_db = _mongo_mod._database

    with patch("main.connect_to_mongo"):
        _mongo_mod._database = fake_db  # type: ignore[assignment]
        try:
            from fastapi.testclient import TestClient as _TC
            with _TC(_main.app) as c:
                yield c
        finally:
            _mongo_mod._database = original_db
            _settings.secret_key = original_secret
            _settings.service_api_key = original_svc_key


def auth_cookie(user: dict) -> dict:
    """Return a dict of cookies with a valid JWT for the given user."""
    from app.config.settings import settings as _settings
    token = _create_token(user, secret=_settings.secret_key)
    return {"silvershade_access_token": token}


def service_headers() -> dict:
    """Return Authorization headers using the test SERVICE_API_KEY."""
    return {"Authorization": "Bearer test-service-api-key"}
