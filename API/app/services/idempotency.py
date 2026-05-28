from datetime import datetime, timezone

from app.database.mongodb import get_database


async def get_cached_idempotency_response(key: str, endpoint: str) -> dict | None:
    """Return a cached response dict if this (key, endpoint) pair was seen before, else None."""
    db = get_database()
    doc = await db.idempotency_cache.find_one({"key": key, "endpoint": endpoint})
    return doc["response"] if doc else None


async def cache_idempotency_response(key: str, endpoint: str, response_data: dict) -> None:
    """Store the response for this idempotency key if not already stored."""
    db = get_database()
    await db.idempotency_cache.update_one(
        {"key": key, "endpoint": endpoint},
        {
            "$setOnInsert": {
                "key": key,
                "endpoint": endpoint,
                "response": response_data,
                "createdAt": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
