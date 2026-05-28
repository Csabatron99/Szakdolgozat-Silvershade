"""
Admin commands cog — ban, kick, givemoney, role.
All commands are hybrid (work as both !prefix and /slash).
Admin-only: caller must have the configured admin role OR Discord Administrator permission.

User ID arguments accept:
  • A raw MongoDB ObjectId  (24 hex chars)
  • A Discord user snowflake (17–20 digit number)
  • A Discord @mention      (<@123456> or <@!123456>)
"""

from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

# Matches both <@123> and <@!123> Discord mention formats.
_MENTION_RE = re.compile(r"<@!?(\d{17,20})>")
# Role mention <@&123> — we only need the numeric portion for the Discord API.
_ROLE_MENTION_RE = re.compile(r"<@&(\d{17,20})>")


def _extract_id(value: str) -> str:
    """Strip @mention formatting and return the bare numeric/hex ID string."""
    value = value.strip()
    m = _MENTION_RE.match(value) or _ROLE_MENTION_RE.match(value)
    return m.group(1) if m else value


class AdminCommands(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        api_client,
        discord_manager,
        config,
    ) -> None:
        self.bot = bot
        self.api = api_client
        self.dm = discord_manager
        self.config = config

    # ── Permission helper ─────────────────────────────────────────────────────

    def _is_admin(self, member: discord.Member | None) -> bool:
        if member is None:
            return False
        has_admin_perm = member.guild_permissions.administrator
        has_admin_role = any(r.name == self.config.admin_role_name for r in member.roles)
        return has_admin_perm or has_admin_role

    async def _require_admin(self, ctx: commands.Context) -> bool:
        if not self._is_admin(ctx.author):  # type: ignore[arg-type]
            await ctx.reply(
                f"You must have the **{self.config.admin_role_name}** role to use this command."
            )
            return False
        return True

    # ── !ban / /ban ───────────────────────────────────────────────────────────

    @commands.hybrid_command(name="ban", description="Ban a user via backend API")
    @app_commands.describe(user="@mention, Discord user ID, or MongoDB user ID", reason="Reason for the ban")
    async def ban(
        self,
        ctx: commands.Context,
        user: str,
        *,
        reason: str = "No reason provided",
    ) -> None:
        if not await self._require_admin(ctx):
            return
        user_id = _extract_id(user)
        try:
            mongo_id, _ = await self.api.resolve_user(user_id)
        except RuntimeError as exc:
            await ctx.reply(f"Could not find user: {exc}")
            return
        try:
            await self.api.ban_user(
                {"userId": mongo_id, "reason": reason, "moderatorId": str(ctx.author.id)}
            )
            await self.dm.send_log(f"User {user_id} was banned. Reason: {reason}")
            await ctx.reply(f"Ban queued for user `{user_id}`.")
        except Exception as exc:
            await ctx.reply(f"Ban failed: {exc}")

    # ── !kick / /kick ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="kick", description="Kick a user via backend API")
    @app_commands.describe(user="@mention, Discord user ID, or MongoDB user ID", reason="Reason for the kick")
    async def kick(
        self,
        ctx: commands.Context,
        user: str,
        *,
        reason: str = "No reason provided",
    ) -> None:
        if not await self._require_admin(ctx):
            return
        user_id = _extract_id(user)
        try:
            mongo_id, _ = await self.api.resolve_user(user_id)
        except RuntimeError as exc:
            await ctx.reply(f"Could not find user: {exc}")
            return
        try:
            await self.api.kick_user(
                {"userId": mongo_id, "reason": reason, "moderatorId": str(ctx.author.id)}
            )
            await self.dm.send_log(f"User {user_id} was kicked. Reason: {reason}")
            await ctx.reply(f"Kick queued for user `{user_id}`.")
        except Exception as exc:
            await ctx.reply(f"Kick failed: {exc}")

    # ── !givemoney / /givemoney ───────────────────────────────────────────────

    @commands.hybrid_command(
        name="givemoney",
        aliases=["give-money", "give_money"],
        description="Add money to a user's balance via backend API",
    )
    @app_commands.describe(
        user="@mention, Discord user ID, or MongoDB user ID",
        amount="Amount to add (use negative to deduct)",
        note="Optional note attached to the transaction",
    )
    async def give_money(
        self,
        ctx: commands.Context,
        user: str,
        amount: float,
        *,
        note: str = "Discord admin transaction",
    ) -> None:
        if not await self._require_admin(ctx):
            return
        if amount == 0:
            await ctx.reply("Amount cannot be zero.")
            return
        user_id = _extract_id(user)
        try:
            mongo_id, user_data = await self.api.resolve_user(user_id)
        except RuntimeError as exc:
            await ctx.reply(f"Could not find user: {exc}")
            return
        display = user_data.get("email") or user_id
        try:
            result = await self.api.adjust_balance(mongo_id, amount)
            data = result.get("data") or result
            new_bal = data.get("balance", "?")
            await self.dm.send_log(
                f"Balance {'added' if amount >= 0 else 'deducted'}: user {display} "
                f"{'+' if amount >= 0 else ''}{amount:.2f} by {ctx.author}"
            )
            await ctx.reply(
                f"Balance updated for **{display}**. "
                f"{'Added' if amount >= 0 else 'Deducted'} `${abs(amount):.2f}`. "
                f"New balance: **${new_bal:.2f}**"
            )
        except Exception as exc:
            await ctx.reply(f"Transaction failed: {exc}")

    # ── !role / /role ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="role", description="Assign or remove a backend role and sync Discord role")
    @app_commands.describe(
        user="@mention, Discord user ID, or MongoDB user ID",
        role_name="Role name to assign or remove (e.g. vip, admin)",
        action="add or remove (default: add)",
    )
    async def role(
        self,
        ctx: commands.Context,
        user: str,
        role_name: str,
        action: str = "add",
    ) -> None:
        if not await self._require_admin(ctx):
            return
        if action not in ("add", "remove"):
            await ctx.reply("Role action must be `add` or `remove`.")
            return
        if not role_name:
            await ctx.reply("Usage: `!role <@user|userId> <roleName> [add|remove]`")
            return
        user_id = _extract_id(user)
        try:
            mongo_id, user_data = await self.api.resolve_user(user_id)
        except RuntimeError as exc:
            await ctx.reply(f"Could not find user: {exc}")
            return
        display = user_data.get("email") or user_id
        try:
            await self.api.assign_role(
                {
                    "userId": mongo_id,
                    "role": role_name,
                    "action": action,
                    "actorId": str(ctx.author.id),
                }
            )
            if action == "add":
                await self.dm.assign_role(user_id, role_name)
            else:
                await self.dm.remove_role(user_id, role_name)
            await ctx.reply(f"Role `{role_name}` {action}ed for **{display}**.")
        except Exception as exc:
            await ctx.reply(f"Role update failed: {exc}")

    # ── !balance / /balance ───────────────────────────────────────────────────

    @commands.hybrid_command(name="balance", description="Check a user's SilverShade balance")
    @app_commands.describe(user="@mention, Discord user ID, or MongoDB user ID (omit to check your own)")
    async def balance(self, ctx: commands.Context, user: str | None = None) -> None:
        if user is None:
            # Self-lookup using caller's Discord ID
            discord_id = str(ctx.author.id)
            try:
                result = await self.api.get_user_by_discord_id(discord_id)
                u = result.get("data") or result
                bal = u.get("balance", 0)
                await ctx.reply(f"Your balance: **${bal:.2f}**")
            except Exception:
                await ctx.reply(
                    "Your Discord account is not linked to a SilverShade account. "
                    "Log in at the website and link your Discord ID."
                )
            return

        if not await self._require_admin(ctx):
            return
        user_id = _extract_id(user)
        try:
            mongo_id, user_data = await self.api.resolve_user(user_id)
        except RuntimeError as exc:
            await ctx.reply(f"Could not find user: {exc}")
            return
        display = user_data.get("email") or user_id
        bal = user_data.get("balance", 0)
        await ctx.reply(f"Balance for **{display}**: **${bal:.2f}**")

    # ── !addbalance / /addbalance ─────────────────────────────────────────────

    @commands.hybrid_command(
        name="addbalance",
        description="Add or subtract from a user's balance (admin only)",
    )
    @app_commands.describe(
        user="@mention, Discord user ID, or MongoDB user ID",
        amount="Amount to add (negative to deduct)",
    )
    async def addbalance(
        self, ctx: commands.Context, user: str, amount: float
    ) -> None:
        if not await self._require_admin(ctx):
            return
        if amount == 0:
            await ctx.reply("Amount cannot be zero.")
            return
        user_id = _extract_id(user)
        try:
            mongo_id, user_data = await self.api.resolve_user(user_id)
        except RuntimeError as exc:
            await ctx.reply(f"Could not find user: {exc}")
            return
        display = user_data.get("email") or user_id
        try:
            result = await self.api.adjust_balance(mongo_id, amount)
            data = result.get("data") or result
            new_bal = data.get("balance", "?")
            verb = "added" if amount >= 0 else "deducted"
            await self.dm.send_log(
                f"Balance {verb}: user {display} {'+' if amount >= 0 else ''}{amount:.2f} by {ctx.author}"
            )
            await ctx.reply(
                f"Balance updated for **{display}**. New balance: **${new_bal:.2f}**"
            )
        except Exception as exc:
            await ctx.reply(f"Balance update failed: {exc}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(
        AdminCommands(bot, bot.api_client, bot.discord_manager, bot.bot_config)  # type: ignore[attr-defined]
    )

    def __init__(
        self,
        bot: commands.Bot,
        api_client,
        discord_manager,
        config,
    ) -> None:
        self.bot = bot
        self.api = api_client
        self.dm = discord_manager
        self.config = config

    # ── Permission helper ─────────────────────────────────────────────────────

    def _is_admin(self, member: discord.Member | None) -> bool:
        if member is None:
            return False
        has_admin_perm = member.guild_permissions.administrator
        has_admin_role = any(r.name == self.config.admin_role_name for r in member.roles)
        return has_admin_perm or has_admin_role

    async def _require_admin(self, ctx: commands.Context) -> bool:
        if not self._is_admin(ctx.author):  # type: ignore[arg-type]
            await ctx.reply(
                f"You must have the **{self.config.admin_role_name}** role to use this command."
            )
            return False
        return True

    # ── !ban / /ban ───────────────────────────────────────────────────────────

    @commands.hybrid_command(name="ban", description="Ban a user via backend API")
    @app_commands.describe(user_id="Discord user ID to ban", reason="Reason for the ban")
    async def ban(
        self,
        ctx: commands.Context,
        user_id: str,
        *,
        reason: str = "No reason provided",
    ) -> None:
        if not await self._require_admin(ctx):
            return
        if not _USER_ID_RE.match(user_id):
            await ctx.reply("Usage: `!ban <userId> [reason]`")
            return
        try:
            await self.api.ban_user(
                {"userId": user_id, "reason": reason, "moderatorId": str(ctx.author.id)}
            )
            await self.dm.send_log(f"User {user_id} was banned. Reason: {reason}")
            await ctx.reply(f"Ban request sent for user `{user_id}`.")
        except Exception as exc:
            await ctx.reply(f"Ban failed: {exc}")

    # ── !kick / /kick ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="kick", description="Kick a user via backend API")
    @app_commands.describe(user_id="Discord user ID to kick", reason="Reason for the kick")
    async def kick(
        self,
        ctx: commands.Context,
        user_id: str,
        *,
        reason: str = "No reason provided",
    ) -> None:
        if not await self._require_admin(ctx):
            return
        if not _USER_ID_RE.match(user_id):
            await ctx.reply("Usage: `!kick <userId> [reason]`")
            return
        try:
            await self.api.kick_user(
                {"userId": user_id, "reason": reason, "moderatorId": str(ctx.author.id)}
            )
            await self.dm.send_log(f"User {user_id} was kicked. Reason: {reason}")
            await ctx.reply(f"Kick request sent for user `{user_id}`.")
        except Exception as exc:
            await ctx.reply(f"Kick failed: {exc}")

    # ── !givemoney / /givemoney ───────────────────────────────────────────────

    @commands.hybrid_command(
        name="givemoney",
        aliases=["give-money", "give_money"],
        description="Create a money transaction via backend API",
    )
    @app_commands.describe(
        user_id="Discord user ID",
        amount="Amount of money to give (positive integer)",
        note="Optional note attached to the transaction",
    )
    async def give_money(
        self,
        ctx: commands.Context,
        user_id: str,
        amount: int,
        *,
        note: str = "Discord admin transaction",
    ) -> None:
        if not await self._require_admin(ctx):
            return
        if not _USER_ID_RE.match(user_id):
            await ctx.reply("Usage: `!givemoney <userId> <amount> [note]`")
            return
        if amount <= 0:
            await ctx.reply("Amount must be a positive integer.")
            return
        try:
            await self.api.create_transaction(
                {
                    "userId": user_id,
                    "amount": amount,
                    "type": "credit",
                    "source": "discord-admin",
                    "note": note,
                    "actorId": str(ctx.author.id),
                }
            )
            await self.dm.send_log(f"User {user_id} received {amount} money via Discord.")
            await ctx.reply(f"Transaction created: `{user_id}` +{amount}")
        except Exception as exc:
            await ctx.reply(f"Transaction failed: {exc}")

    # ── !role / /role ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="role", description="Assign backend role and sync Discord role")
    @app_commands.describe(
        user_id="Discord user ID",
        role_name="Role name to assign or remove",
        action="add or remove (default: add)",
    )
    async def role(
        self,
        ctx: commands.Context,
        user_id: str,
        role_name: str,
        action: str = "add",
    ) -> None:
        if not await self._require_admin(ctx):
            return
        if not _USER_ID_RE.match(user_id) or not role_name:
            await ctx.reply("Usage: `!role <userId> <roleName> [add|remove]`")
            return
        if action not in ("add", "remove"):
            await ctx.reply("Role action must be `add` or `remove`.")
            return
        try:
            await self.api.assign_role(
                {
                    "userId": user_id,
                    "role": role_name,
                    "action": action,
                    "actorId": str(ctx.author.id),
                }
            )
            if action == "add":
                await self.dm.assign_role(user_id, role_name)
            else:
                await self.dm.remove_role(user_id, role_name)
            await ctx.reply(f"Role `{role_name}` {action} completed for `{user_id}`.")
        except Exception as exc:
            await ctx.reply(f"Role update failed: {exc}")

    # ── !balance / /balance ───────────────────────────────────────────────────

    @commands.hybrid_command(name="balance", description="Check a user's balance (admin only)")
    @app_commands.describe(user_id="User ID to check")
    async def balance(self, ctx: commands.Context, user_id: str) -> None:
        if not await self._require_admin(ctx):
            return
        if not _USER_ID_RE.match(user_id):
            await ctx.reply("Usage: `!balance <userId>`")
            return
        try:
            result = await self.api.get_user(user_id)
            u = result.get("data") or result
            bal = u.get("balance", 0)
            await ctx.reply(f"User `{user_id}` balance: **${bal:.2f}**")
        except Exception as exc:
            await ctx.reply(f"Failed to fetch balance: {exc}")

    # ── !addbalance / /addbalance ─────────────────────────────────────────────

    @commands.hybrid_command(
        name="addbalance",
        description="Add or subtract from a user's balance (admin only)",
    )
    @app_commands.describe(
        user_id="User ID to update",
        amount="Amount to add (negative to deduct)",
    )
    async def addbalance(
        self, ctx: commands.Context, user_id: str, amount: float
    ) -> None:
        if not await self._require_admin(ctx):
            return
        if not _USER_ID_RE.match(user_id):
            await ctx.reply("Usage: `!addbalance <userId> <amount>`")
            return
        try:
            result = await self.api.adjust_balance(user_id, amount)
            data = result.get("data") or result
            new_bal = data.get("balance", "?")
            verb = "added" if amount >= 0 else "deducted"
            await self.dm.send_log(
                f"Balance {verb}: user {user_id} {'+' if amount >= 0 else ''}{amount:.2f} by {ctx.author}"
            )
            await ctx.reply(
                f"Balance updated for `{user_id}`. New balance: **${new_bal:.2f}**"
            )
        except Exception as exc:
            await ctx.reply(f"Balance update failed: {exc}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(
        AdminCommands(bot, bot.api_client, bot.discord_manager, bot.bot_config)  # type: ignore[attr-defined]
    )
