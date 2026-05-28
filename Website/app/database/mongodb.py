from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config.settings import settings

_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


def connect_to_mongo() -> None:
    global _client, _database
    _client = AsyncIOMotorClient(settings.mongodb_uri)
    _database = _client[settings.mongodb_db]


def close_mongo_connection() -> None:
    global _client
    if _client:
        _client.close()


def get_database() -> AsyncIOMotorDatabase:
    if _database is None:
        raise RuntimeError("MongoDB is not initialized. Call connect_to_mongo first.")
    return _database
