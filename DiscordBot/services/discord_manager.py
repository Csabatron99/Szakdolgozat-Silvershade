"""
Discord guild helper — channel logging, role management, sync payload processing.
Mirrors the functionality of the original services/discordManager.js.
"""

from __future__ import annotations

import logging

import discord


class DiscordManager:
    def __init__(self, bot: discord.ext.commands.Bot, config, api_client, logger: logging.Logger) -> None:  # type: ignore[name-defined]
        self._bot = bot
        self._config = config
        self._api = api_client
        self._logger = logger

    # ── Logging ───────────────────────────────────────────────────────────────

    async def send_log(self, message: str) -> None:
        """Send a message to every configured log channel."""
        for channel_id in self._config.log_channel_ids:
            try:
                channel = self._bot.get_channel(int(channel_id))
                if channel is None:
                    channel = await self._bot.fetch_channel(int(channel_id))
                if isinstance(channel, discord.abc.Messageable):
                    await channel.send(message)
            except Exception as exc:
                self._logger.warning("Failed sending log to channel %s: %s", channel_id, exc)

    # ── Guild / member helpers ────────────────────────────────────────────────

    async def _fetch_member(self, user_id: str) -> discord.Member:
        guild = self._bot.get_guild(int(self._config.discord_guild_id))
        if guild is None:
            guild = await self._bot.fetch_guild(int(self._config.discord_guild_id))
        return await guild.fetch_member(int(user_id))

    # ── Role management ───────────────────────────────────────────────────────

    async def assign_role(self, user_id: str, role_name: str) -> None:
        member = await self._fetch_member(user_id)
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role is None:
            raise ValueError(f'Discord role "{role_name}" not found')
        await member.add_roles(role)

    async def remove_role(self, user_id: str, role_name: str) -> None:
        member = await self._fetch_member(user_id)
        role = discord.utils.get(member.guild.roles, name=role_name)
        if role is None:
            raise ValueError(f'Discord role "{role_name}" not found')
        await member.remove_roles(role)

    async def sync_backend_roles(self, user_id: str, backend_roles: list[str]) -> None:
        """Sync backend role names to Discord role IDs using BACKEND_ROLE_MAP."""
        member = await self._fetch_member(user_id)
        role_map = self._config.backend_role_map
        mapped_ids = {role_map[r] for r in backend_roles if r in role_map}
        managed_ids = set(role_map.values())

        # Remove Discord roles that are no longer in the backend list.
        for role in member.roles:
            if str(role.id) in managed_ids and str(role.id) not in mapped_ids:
                await member.remove_roles(role)

        # Add Discord roles that are missing.
        for role_id in mapped_ids:
            if not member.get_role(int(role_id)):
                await member.add_roles(discord.Object(id=int(role_id)))

    # ── Sync payload processing ───────────────────────────────────────────────

    async def _handle_action_log(self, action: dict) -> None:
        action_type = action.get("type", "")
        user_id = action.get("userId") or action.get("playerId") or "unknown"
        if action_type == "ban":
            await self.send_log(f"User {user_id} was banned")
        elif action_type == "kick":
            await self.send_log(f"User {user_id} was kicked")
        elif action_type == "give_money":
            await self.send_log(f"User {user_id} received {action.get('amount')} money")
        else:
            await self.send_log(f"Admin action: {action_type}")

    async def process_sync_payload(self, payload: dict) -> None:
        """Apply pending admin actions and role updates to Discord.

        FiveM reward transactions are intentionally ignored here — FiveM delivers
        the in-game reward and confirms the transaction.  Stripe purchases never
        appear in the sync feed (filtered server-side).  A thank-you message for
        completed Stripe purchases is sent directly from the webhook handler.
        """
        admin_actions = (
            payload.get("pendingAdminActions") or payload.get("adminActions") or []
        )
        role_updates = payload.get("roleUpdates") or []

        for action in admin_actions:
            await self._handle_action_log(action)
            # §6.1 — confirm the action so the backend stops re-sending it.
            action_id = action.get("id") or action.get("_id")
            if action_id:
                try:
                    await self._api.confirm_admin_action(str(action_id))
                except Exception as exc:
                    self._logger.warning(
                        "Failed to confirm admin action %s: %s", action_id, exc
                    )

        for role_update in role_updates:
            uid = role_update.get("userId", "")
            await self.sync_backend_roles(uid, role_update.get("roles") or [])
            await self.send_log(f"Roles synchronized for user {uid}")
