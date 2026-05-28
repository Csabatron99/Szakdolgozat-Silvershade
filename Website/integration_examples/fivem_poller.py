"""Dummy FiveM poller example.

This script simulates server-side polling of pending transactions and admin actions.
"""

import os

import requests

BASE_URL = os.getenv("SILVERSHADE_API", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.getenv("SILVERSHADE_API_KEY", "replace_with_service_api_key")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def api_base_url() -> str:
    return BASE_URL[:-4] if BASE_URL.endswith("/api") else BASE_URL


def run_cycle() -> None:
    sync_updates = requests.get(f"{api_base_url()}/api/sync/updates", headers=HEADERS, timeout=15)
    sync_updates.raise_for_status()
    payload = sync_updates.json()

    for transaction in payload.get("pendingTransactions", []):
        # Replace with actual FiveM reward execution logic.
        print(f"Rewarding transaction {transaction['id']} for user {transaction['userId']}")
        confirm = {
            "transactionId": transaction["id"],
            "status": "completed",
        }
        requests.post(f"{api_base_url()}/api/confirm-transaction", headers=HEADERS, json=confirm, timeout=15).raise_for_status()

    for action in payload.get("pendingAdminActions", []):
        # Replace with actual FiveM admin execution logic.
        print(f"Executing action {action['type']} for player {action['playerId']}")
        confirm = {
            "actionId": action["id"],
            "status": "completed",
        }
        requests.post(f"{api_base_url()}/api/confirm-admin-action", headers=HEADERS, json=confirm, timeout=15).raise_for_status()


if __name__ == "__main__":
    run_cycle()
