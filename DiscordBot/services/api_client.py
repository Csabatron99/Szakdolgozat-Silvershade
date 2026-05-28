"""
Async HTTP client for the SilverShade API.
Mirrors the functionality of the original services/apiClient.js.
"""

from __future__ import annotations

import logging
import re

import httpx

_DISCORD_SNOWFLAKE_RE = re.compile(r"^\d{17,20}$")
_MONGODB_ID_RE = re.compile(r"^[0-9a-f]{24}$", re.IGNORECASE)


class ApiClient:
    def __init__(self, config, logger: logging.Logger) -> None:
        self._logger = logger
        self._admin_token: str | None = config.admin_token
        self._client = httpx.AsyncClient(
            base_url=config.api_base_url,
            timeout=10.0,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _sanitize_error(self, exc: httpx.HTTPStatusError) -> dict:
        try:
            body = exc.response.json()
            message = (
                (body.get("error") or {}).get("message")
                or body.get("message")
                or "API request failed"
            )
        except Exception:
            message = "API request failed"
        return {"status": exc.response.status_code, "message": message}

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        try:
            resp = await self._client.request(method, url, json=json, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            safe = self._sanitize_error(exc)
            self._logger.error("API %s %s failed: %s", method.upper(), url, safe["message"])
            raise RuntimeError(safe["message"]) from exc
        except Exception as exc:
            self._logger.error("API %s %s error: %s", method.upper(), url, exc)
            raise RuntimeError(str(exc)) from exc

    # ── User endpoints ────────────────────────────────────────────────────────

    async def get_user(self, user_id: str) -> dict:
        return await self._request("GET", f"/api/v1/service/users/{user_id}")

    async def get_user_by_discord_id(self, discord_id: str) -> dict:
        """Look up a registered user by their Discord snowflake ID."""
        return await self._request("GET", f"/api/v1/service/users/discord/{discord_id}")

    async def resolve_user(self, id_input: str) -> tuple[str, dict]:
        """
        Resolve a Discord snowflake or MongoDB ObjectId to (mongodb_id, user_data).
        Raises RuntimeError if the user is not found or the ID format is invalid.
        """
        if _DISCORD_SNOWFLAKE_RE.match(id_input):
            data = await self.get_user_by_discord_id(id_input)
            user = data.get("data") or data
            return str(user["id"]), user
        if _MONGODB_ID_RE.match(id_input):
            data = await self.get_user(id_input)
            user = data.get("data") or data
            return id_input, user
        raise RuntimeError(f"'{id_input}' is not a valid Discord ID or User ID.")


    # ── Admin action endpoints ────────────────────────────────────────────────

    async def ban_user(self, payload: dict) -> dict:
        return await self._request(
            "POST",
            "/api/v1/service/admin-actions",
            json={
                "type": "ban",
                "playerId": str(payload.get("userId", "")),
                "data": {
                    "reason": payload.get("reason", "No reason provided"),
                    "moderatorId": payload.get("moderatorId", ""),
                },
            },
        )

    async def kick_user(self, payload: dict) -> dict:
        return await self._request(
            "POST",
            "/api/v1/service/admin-actions",
            json={
                "type": "kick",
                "playerId": str(payload.get("userId", "")),
                "data": {
                    "reason": payload.get("reason", "No reason provided"),
                    "moderatorId": payload.get("moderatorId", ""),
                },
            },
        )

    # ── Transaction endpoints ─────────────────────────────────────────────────

    async def create_transaction(self, payload: dict) -> dict:
        """Give money to a user — delegates to the balance adjust service endpoint.
        NOTE: userId must be a MongoDB ObjectId string, not a Discord snowflake ID.
        """
        return await self.adjust_balance(
            str(payload.get("userId", "")),
            float(payload.get("amount", 0)),
        )

    async def get_recent_transactions(self, limit: int = 10) -> dict:
        return await self._request(
            "GET", "/api/v1/service/transactions", params={"limit": limit}
        )

    async def get_user_transactions(self, user_id: str, limit: int = 10) -> dict:
        return await self._request(
            "GET",
            f"/api/v1/service/users/{user_id}/transactions",
            params={"limit": limit},
        )

    # ── Store endpoints ───────────────────────────────────────────────────────

    async def get_store_items(self) -> dict:
        return await self._request("GET", "/api/v1/service/store")

    # ── Balance endpoint ──────────────────────────────────────────────────────

    async def adjust_balance(self, user_id: str, amount: float) -> dict:
        return await self._request(
            "PATCH",
            f"/api/v1/service/users/{user_id}/balance",
            json={"amount": amount},
        )

    # ── Role endpoints ────────────────────────────────────────────────────────

    async def assign_role(self, payload: dict) -> dict:
        action = payload.get("action", "add")
        action_type = "give_role" if action == "add" else "remove_role"
        return await self._request(
            "POST",
            "/api/v1/service/admin-actions",
            json={
                "type": action_type,
                "playerId": str(payload.get("userId", "")),
                "data": {"role": payload.get("role", "")},
            },
        )

    async def update_discord_role(self, payload: dict) -> dict:
        """Deprecated — use assign_role instead. Kept for backward compatibility."""
        return await self.assign_role(payload)

    # ── Sync / polling ────────────────────────────────────────────────────────

    async def poll_updates(self, cursor: str | None = None) -> dict:
        params: dict = {}
        if cursor is not None:
            params["cursor"] = cursor
        return await self._request("GET", "/api/v1/sync/updates", params=params)

    async def confirm_admin_action(
        self, action_id: str, status: str = "completed"
    ) -> dict:
        """§6.1 — confirm the action so the backend marks it as processed."""
        return await self._request(
            "PATCH",
            f"/api/v1/admin-actions/{action_id}/status",
            json={"status": status},
        )

    # ── Simulation (test helper) ──────────────────────────────────────────────

    async def simulate_discord_pickup(self) -> dict:
        try:
            resp = await self._client.post(
                "/api/v1/admin/simulate-discord-pickup",
                headers={"Authorization": f"Bearer {self._admin_token}"},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            safe = self._sanitize_error(exc)
            self._logger.error(
                "API POST /api/v1/admin/simulate-discord-pickup failed: %s",
                safe["message"],
            )
            raise RuntimeError(safe["message"]) from exc
