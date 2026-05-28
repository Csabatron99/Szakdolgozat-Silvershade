"""Dummy Discord bot integration example.

Shows how a bot could read pending admin actions or transactions.
"""

import os

import requests

BASE_URL = os.getenv("SILVERSHADE_API", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.getenv("SILVERSHADE_API_KEY", "replace_with_service_api_key")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def api_base_url() -> str:
    return BASE_URL[:-4] if BASE_URL.endswith("/api") else BASE_URL


def fetch_queues() -> None:
    sync_updates = requests.get(f"{api_base_url()}/api/sync/updates", headers=HEADERS, timeout=15)
    sync_updates.raise_for_status()
    payload = sync_updates.json()

    print("Pending transactions:", len(payload.get("pendingTransactions", [])))
    print("Pending admin actions:", len(payload.get("pendingAdminActions", [])))


if __name__ == "__main__":
    fetch_queues()
