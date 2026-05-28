"""
seed_data.py — Populate the SilverShade database with realistic dummy data.

Usage (from repo root, with API venv active):
    cd C:\ProgramThesis
    .\.venv\Scripts\python.exe seed_data.py
  or
    python seed_data.py          # if .venv is already activated

What it creates (idempotent — safe to run multiple times):
  Users:
    admin@silvershade.gg  /  Admin1234!   (role: admin)
    alice@test.com        /  Test1234!    (role: user, FiveM + Discord linked)
    bob@test.com          /  Test1234!    (role: user, Discord linked)
    charlie@test.com      /  Test1234!    (role: user)

  Store items:
    VIP Pass        — $19.99  (money reward 5000)
    Starter Kit     — $9.99   (item reward)
    Premium Role    — $29.99  (role reward: vip)

  Top-up packages:
    $5 Credits   — $5.00
    $10 Credits  — $10.00
    $25 Credits  — $25.00
    $50 Credits  — $50.00

  Transactions (for alice):
    completed topup (+$25), completed store purchase (VIP Pass, -$19.99), pending purchase (Premium Role)

  Admin actions (queued — ready for FiveM/Discord pickup):
    give_money    (target: alice's fivem_id, amount 1000)
    assign_role   (target: bob's discord_id, role: vip)
    ban           (target: charlie, reason: "Testing ban flow")
"""

import asyncio
import sys
from datetime import datetime, timezone, timedelta

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# ── resolve the API package from within repo root ────────────────────────────
import importlib.util, pathlib

_api_root = pathlib.Path(__file__).parent / "API"
if str(_api_root) not in sys.path:
    sys.path.insert(0, str(_api_root))

from app.config.settings import settings
from app.services.security import hash_password

# ─────────────────────────────────────────────────────────────────────────────

def now_utc():
    return datetime.now(timezone.utc)


def past(days=0, hours=0, minutes=0):
    return now_utc() - timedelta(days=days, hours=hours, minutes=minutes)


# ─────────────────────────────────────────────────────────────────────────────

USERS = [
    {
        "email": "admin@silvershade.gg",
        "password": "Admin1234!",
        "role": "admin",
        "balance": 0.0,
        "is_active": True,
        "is_banned": False,
        "discord_id": None,
        "fivem_id": None,
    },
    {
        "email": "alice@test.com",
        "password": "Test1234!",
        "role": "user",
        "balance": 50.0,
        "is_active": True,
        "is_banned": False,
        "discord_id": "alice_discord_123456",
        "fivem_id": "alice_fivem_7890",
    },
    {
        "email": "bob@test.com",
        "password": "Test1234!",
        "role": "user",
        "balance": 10.0,
        "is_active": True,
        "is_banned": False,
        "discord_id": "bob_discord_654321",
        "fivem_id": None,
    },
    {
        "email": "charlie@test.com",
        "password": "Test1234!",
        "role": "user",
        "balance": 0.0,
        "is_active": True,
        "is_banned": False,
        "discord_id": None,
        "fivem_id": "charlie_fivem_1111",
    },
]

STORE_ITEMS = [
    {
        "name": "VIP Pass",
        "description": "Grants VIP status in-game for 30 days. Includes exclusive vehicle spawns and priority queue.",
        "price": 19.99,
        "reward_type": "money",
        "reward_value": 5000,
        "stock": -1,
        "is_active": True,
    },
    {
        "name": "Starter Kit",
        "description": "Jump-start your FiveM experience with a curated package of beginner items and gear.",
        "price": 9.99,
        "reward_type": "item",
        "reward_value": "starter_kit_bundle",
        "stock": -1,
        "is_active": True,
    },
    {
        "name": "Premium Role",
        "description": "Unlock the Premium Discord role and in-game perks for 60 days.",
        "price": 29.99,
        "reward_type": "role",
        "reward_value": "premium",
        "stock": -1,
        "is_active": True,
    },
]

TOPUP_PACKAGES = [
    {"name": "$5 Credits",  "amount": 5.00,  "is_active": True},
    {"name": "$10 Credits", "amount": 10.00, "is_active": True},
    {"name": "$25 Credits", "amount": 25.00, "is_active": True},
    {"name": "$50 Credits", "amount": 50.00, "is_active": True},
]


# ─────────────────────────────────────────────────────────────────────────────

async def upsert_user(col, data: dict) -> ObjectId:
    """Insert user or return existing id without modifying password."""
    existing = await col.find_one({"email": data["email"]})
    if existing:
        print(f"  [skip]   user already exists: {data['email']}")
        return existing["_id"]

    doc = {k: v for k, v in data.items() if k != "password"}
    doc["hashed_password"] = hash_password(data["password"])
    doc["created_at"] = past(days=7)
    doc["updated_at"] = past(days=7)
    result = await col.insert_one(doc)
    print(f"  [create] user: {data['email']}  (id={result.inserted_id})")
    return result.inserted_id


async def upsert_store_item(col, data: dict) -> ObjectId:
    existing = await col.find_one({"name": data["name"]})
    if existing:
        print(f"  [skip]   store item already exists: {data['name']}")
        return existing["_id"]
    doc = {**data, "created_at": past(days=5), "updated_at": past(days=5)}
    result = await col.insert_one(doc)
    print(f"  [create] store item: {data['name']}  (id={result.inserted_id})")
    return result.inserted_id


async def upsert_topup_package(col, data: dict) -> ObjectId:
    existing = await col.find_one({"name": data["name"]})
    if existing:
        print(f"  [skip]   topup package already exists: {data['name']}")
        return existing["_id"]
    doc = {**data, "created_at": past(days=5), "updated_at": past(days=5)}
    result = await col.insert_one(doc)
    print(f"  [create] topup package: {data['name']}  (id={result.inserted_id})")
    return result.inserted_id


async def seed_transactions(col, alice_id: ObjectId, vip_item_id: ObjectId, premium_item_id: ObjectId):
    """Create sample transactions for alice only if none exist for her."""
    existing = await col.count_documents({"user_id": str(alice_id)})
    if existing > 0:
        print(f"  [skip]   transactions already exist for alice ({existing} found)")
        return

    transactions = [
        {
            "user_id": str(alice_id),
            "type": "topup",
            "amount": 25.00,
            "status": "completed",
            "description": "Top-up: $25 Credits",
            "stripe_session_id": "cs_test_seed_topup_001",
            "item_id": None,
            "created_at": past(days=3),
            "updated_at": past(days=3),
        },
        {
            "user_id": str(alice_id),
            "type": "purchase",
            "amount": -19.99,
            "status": "completed",
            "description": "Store purchase: VIP Pass",
            "stripe_session_id": None,
            "item_id": str(vip_item_id),
            "created_at": past(days=2),
            "updated_at": past(days=2),
        },
        {
            "user_id": str(alice_id),
            "type": "purchase",
            "amount": -29.99,
            "status": "pending",
            "description": "Store purchase: Premium Role",
            "stripe_session_id": None,
            "item_id": str(premium_item_id),
            "created_at": past(hours=3),
            "updated_at": past(hours=3),
        },
    ]
    result = await col.insert_many(transactions)
    print(f"  [create] {len(result.inserted_ids)} transactions for alice")


async def seed_admin_actions(
    col,
    alice_id: ObjectId,
    bob_id: ObjectId,
    charlie_id: ObjectId,
):
    """Create queued admin actions only if none are pending."""
    existing = await col.count_documents({"status": "pending"})
    if existing > 0:
        print(f"  [skip]   pending admin actions already exist ({existing} found)")
        return

    actions = [
        {
            "type": "give_money",
            "target_user_id": str(alice_id),
            "target_fivem_id": "alice_fivem_7890",
            "data": {"amount": 1000},
            "status": "pending",
            "source": "web",
            "created_at": past(hours=1),
            "updated_at": past(hours=1),
            "confirmed_at": None,
        },
        {
            "type": "assign_role",
            "target_user_id": str(bob_id),
            "target_discord_id": "bob_discord_654321",
            "data": {"role": "vip"},
            "status": "pending",
            "source": "web",
            "created_at": past(hours=2),
            "updated_at": past(hours=2),
            "confirmed_at": None,
        },
        {
            "type": "ban",
            "target_user_id": str(charlie_id),
            "target_discord_id": None,
            "data": {"reason": "Testing ban flow", "duration": "permanent"},
            "status": "pending",
            "source": "discord",
            "created_at": past(minutes=30),
            "updated_at": past(minutes=30),
            "confirmed_at": None,
        },
    ]
    result = await col.insert_many(actions)
    print(f"  [create] {len(result.inserted_ids)} pending admin actions")


# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print("\n── SilverShade Seed Data ─────────────────────────────────────────")
    print(f"  MongoDB URI : {settings.mongodb_uri}")
    print(f"  Database    : {settings.mongodb_db}")
    print("──────────────────────────────────────────────────────────────────\n")

    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db]

    print("── Users ─────────────────────────────────────────────────────────")
    user_ids = {}
    for u in USERS:
        uid = await upsert_user(db.users, u)
        user_ids[u["email"]] = uid

    print("\n── Store Items ───────────────────────────────────────────────────")
    item_ids = {}
    for item in STORE_ITEMS:
        iid = await upsert_store_item(db.store_items, item)
        item_ids[item["name"]] = iid

    print("\n── Top-up Packages ───────────────────────────────────────────────")
    for pkg in TOPUP_PACKAGES:
        await upsert_topup_package(db.topup_packages, pkg)

    print("\n── Transactions (alice) ──────────────────────────────────────────")
    await seed_transactions(
        db.transactions,
        alice_id=user_ids["alice@test.com"],
        vip_item_id=item_ids["VIP Pass"],
        premium_item_id=item_ids["Premium Role"],
    )

    print("\n── Admin Actions (pending) ───────────────────────────────────────")
    await seed_admin_actions(
        db.admin_actions,
        alice_id=user_ids["alice@test.com"],
        bob_id=user_ids["bob@test.com"],
        charlie_id=user_ids["charlie@test.com"],
    )

    client.close()

    print("\n──────────────────────────────────────────────────────────────────")
    print("  Done. Summary of seeded accounts:")
    print()
    print("  Role   | Email                   | Password   | Balance")
    print("  -------|-------------------------|------------|--------")
    print("  admin  | admin@silvershade.gg    | Admin1234! | —")
    print("  user   | alice@test.com          | Test1234!  | $50.00")
    print("  user   | bob@test.com            | Test1234!  | $10.00")
    print("  user   | charlie@test.com        | Test1234!  | $0.00")
    print()
    print("  3 pending admin actions queued (give_money, assign_role, ban)")
    print("  3 transactions seeded for alice (topup, purchase, pending)")
    print("──────────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    asyncio.run(main())
