"""
General commands cog — ping, user, transactions.
All commands are hybrid (work as both !prefix and /slash).
Available to all server members.

User ID arguments accept:
  • A raw MongoDB ObjectId  (24 hex chars)
  • A Discord user snowflake (17–20 digit number)
  • A Discord @mention      (<@123456> or <@!123456>)
"""

from __future__ import annotations

import re

from discord import app_commands
from discord.ext import commands

_MENTION_RE = re.compile(r"<@!?(\d{17,20})>")


def _extract_id(value: str) -> str:
    """Strip @mention formatting and return the bare numeric/hex ID string."""
    value = value.strip()
    m = _MENTION_RE.match(value)
    return m.group(1) if m else value


class GeneralCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, api_client, config) -> None:
        self.bot = bot
        self.api = api_client
        self.config = config

    # ── !ping / /ping ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="ping", description="Test bot availability")
    async def ping(self, ctx: commands.Context) -> None:
        latency_ms = round(self.bot.latency * 1000)
        await ctx.reply(f"Pong! Latency: **{latency_ms}ms**")

    # ── !user / /user ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="user", description="Fetch user data from the backend API")
    @app_commands.describe(user="@mention, Discord user ID, or MongoDB user ID (omit to look up yourself)")
    async def user(self, ctx: commands.Context, user: str | None = None) -> None:
        # Default to caller's own Discord ID
        id_input = _extract_id(user) if user else str(ctx.author.id)
        try:
            mongo_id, u = await self.api.resolve_user(id_input)
        except RuntimeError as exc:
            await ctx.reply(str(exc))
            return
        discord_linked = "✅" if u.get("discord_id") else "❌"
        fivem_linked = "✅" if u.get("fivem_id") else "❌"
        await ctx.reply(
            f"**{u.get('email') or 'n/a'}**\n"
            f"Role: `{u.get('role', 'user')}` | Balance: **${u.get('balance', 0):.2f}**\n"
            f"Discord linked: {discord_linked} | FiveM linked: {fivem_linked}"
        )

    # ── !transactions / /transactions ─────────────────────────────────────────

    @commands.hybrid_command(
        name="transactions",
        description="List recent transactions (admin only)",
    )
    @app_commands.describe(limit="Number of transactions to show (1–20, default 5)")
    async def transactions(self, ctx: commands.Context, limit: int = 5) -> None:
        if not 1 <= limit <= 20:
            await ctx.reply("Limit must be between 1 and 20.")
            return
        try:
            result = await self.api.get_recent_transactions(limit)
            items = result.get("data") or result
            if not isinstance(items, list) or not items:
                await ctx.reply("No transactions found.")
                return
            lines = [
                f"`{(tx.get('id') or tx.get('_id') or '')[:8]}…` "
                f"{tx.get('type', '?')} **${abs(float(tx.get('amount', 0))):.2f}** "
                f"— {tx.get('status', '?')}"
                for tx in items
            ]
            await ctx.reply("Recent transactions:\n" + "\n".join(lines))
        except Exception as exc:
            await ctx.reply(f"Failed to load transactions: {exc}")

    # ── !store / /store ───────────────────────────────────────────────────────

    @commands.hybrid_command(name="store", description="List available store items")
    async def store(self, ctx: commands.Context) -> None:
        try:
            result = await self.api.get_store_items()
            items = result.get("data") or result
            if not isinstance(items, list) or not items:
                await ctx.reply("No store items found.")
                return
            lines = [
                f"**{item.get('name')}** — ${item.get('price', 0):.2f}"
                for item in items
            ]
            await ctx.reply("Store items:\n" + "\n".join(lines))
        except Exception as exc:
            await ctx.reply(f"Failed to load store: {exc}")

    # ── !history / /history ───────────────────────────────────────────────────

    @commands.hybrid_command(
        name="history",
        description="Show recent transactions for a user",
    )
    @app_commands.describe(
        user="@mention, Discord user ID, or MongoDB user ID",
        limit="Number of transactions (1–20, default 5)",
    )
    async def history(
        self,
        ctx: commands.Context,
        user: str,
        limit: int = 5,
    ) -> None:
        if not 1 <= limit <= 20:
            await ctx.reply("Limit must be between 1 and 20.")
            return
        user_id = _extract_id(user)
        try:
            mongo_id, user_data = await self.api.resolve_user(user_id)
        except RuntimeError as exc:
            await ctx.reply(f"Could not find user: {exc}")
            return
        display = user_data.get("email") or user_id
        try:
            result = await self.api.get_user_transactions(mongo_id, limit)
            items = result.get("data") or result
            if not isinstance(items, list) or not items:
                await ctx.reply(f"No transactions found for **{display}**.")
                return
            lines = [
                f"{tx.get('type', '?')} **${abs(float(tx.get('amount', 0))):.2f}** "
                f"— {tx.get('status', '?')}"
                for tx in items
            ]
            await ctx.reply(f"Transactions for **{display}**:\n" + "\n".join(lines))
        except Exception as exc:
            await ctx.reply(f"Failed to load history: {exc}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(
        GeneralCommands(bot, bot.api_client, bot.bot_config)  # type: ignore[attr-defined]
    )

    def __init__(self, bot: commands.Bot, api_client, config) -> None:
        self.bot = bot
        self.api = api_client
        self.config = config

    # ── !ping / /ping ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="ping", description="Test bot availability")
    async def ping(self, ctx: commands.Context) -> None:
        await ctx.reply("Pong!")

    # ── !user / /user ─────────────────────────────────────────────────────────

    @commands.hybrid_command(name="user", description="Fetch user data from the backend API")
    @app_commands.describe(user_id="Discord user ID (defaults to your own)")
    async def user(self, ctx: commands.Context, user_id: str | None = None) -> None:
        target = user_id or str(ctx.author.id)
        if not _USER_ID_RE.match(target):
            await ctx.reply("Invalid user ID. Only numeric IDs are accepted.")
            return
        try:
            result = await self.api.get_user(target)
            u = result.get("data") or result
            await ctx.reply(
                f"User `{u.get('id')}` | "
                f"name: {u.get('name') or 'n/a'} | "
                f"balance: {u.get('balance', 0)}"
            )
        except Exception as exc:
            await ctx.reply(f"Failed to fetch user data: {exc}")

    # ── !transactions / /transactions ─────────────────────────────────────────

    @commands.hybrid_command(
        name="transactions",
        description="List recent transactions from the backend API",
    )
    @app_commands.describe(limit="Number of transactions to show (1–20, default 5)")
    async def transactions(self, ctx: commands.Context, limit: int = 5) -> None:
        if not 1 <= limit <= 20:
            await ctx.reply("Usage: `!transactions [1-20]`")
            return
        try:
            result = await self.api.get_recent_transactions(limit)
            items = result.get("data") or result
            if not isinstance(items, list) or not items:
                await ctx.reply("No transactions found.")
                return
            lines = [
                f"{tx.get('id')}: {tx.get('userId')} {tx.get('type')} "
                f"{tx.get('amount')} ({tx.get('createdAt', 'n/a')})"
                for tx in items
            ]
            await ctx.reply("Recent transactions:\n" + "\n".join(lines))
        except Exception as exc:
            await ctx.reply(f"Failed to load transactions: {exc}")


    # ── !store / /store ───────────────────────────────────────────────────────

    @commands.hybrid_command(name="store", description="List available store items")
    async def store(self, ctx: commands.Context) -> None:
        try:
            result = await self.api.get_store_items()
            items = result.get("data") or result
            if not isinstance(items, list) or not items:
                await ctx.reply("No store items found.")
                return
            lines = [
                f"`{item.get('id')}` — **{item.get('name')}** — ${item.get('price', 0):.2f}"
                for item in items
            ]
            await ctx.reply("Store items:\n" + "\n".join(lines))
        except Exception as exc:
            await ctx.reply(f"Failed to load store: {exc}")

    # ── !history / /history ───────────────────────────────────────────────────

    @commands.hybrid_command(
        name="history",
        description="Show recent transactions for a user",
    )
    @app_commands.describe(
        user_id="User ID to look up (admin only for others)",
        limit="Number of transactions (1–20, default 5)",
    )
    async def history(
        self,
        ctx: commands.Context,
        user_id: str,
        limit: int = 5,
    ) -> None:
        if not _USER_ID_RE.match(user_id):
            await ctx.reply("Invalid user ID.")
            return
        if not 1 <= limit <= 20:
            await ctx.reply("Limit must be between 1 and 20.")
            return
        try:
            result = await self.api.get_user_transactions(user_id, limit)
            items = result.get("data") or result
            if not isinstance(items, list) or not items:
                await ctx.reply(f"No transactions found for `{user_id}`.")
                return
            lines = [
                f"{tx.get('type')} {tx.get('amount')} — {tx.get('status')} ({tx.get('createdAt', 'n/a')})"
                for tx in items
            ]
            await ctx.reply(f"Transactions for `{user_id}`:\n" + "\n".join(lines))
        except Exception as exc:
            await ctx.reply(f"Failed to load history: {exc}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(
        GeneralCommands(bot, bot.api_client, bot.bot_config)  # type: ignore[attr-defined]
    )
