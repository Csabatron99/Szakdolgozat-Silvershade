"""
SilverShade Discord Bot — Python rewrite of the original Node.js/discord.js bot.

Features:
  - Prefix commands  (!ban, !kick, !givemoney, !role, !ping, !user, !transactions)
  - Slash commands   (/ban, /kick, /givemoney, /role, /ping, /user, /transactions)
  - Background polling of /api/v1/sync/updates every N seconds
  - §6.1 fix: confirms each admin action after processing so backend stops resending

Environment variables (see .env.example):
  DISCORD_TOKEN, DISCORD_GUILD_ID, SILVERSHADE_API, SILVERSHADE_API_KEY
  Optional: DISCORD_CLIENT_ID, COMMAND_PREFIX, ADMIN_ROLE_NAME, LOG_CHANNEL_IDS,
            POLL_INTERVAL_MS, BACKEND_ROLE_MAP, SILVERSHADE_ADMIN_TOKEN

Usage:
  python bot.py                         — normal operation
  python bot.py --simulate-discord-pickup — fire test simulation and exit
"""

from __future__ import annotations

import asyncio
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

from config import Config, validate_config
from services.api_client import ApiClient
from services.discord_manager import DiscordManager
from services.logger import get_logger

load_dotenv()

logger = get_logger("bot")

# ── Configuration ─────────────────────────────────────────────────────────────

config = Config()

try:
    validate_config(config)
except ValueError as exc:
    logger.error(str(exc))
    sys.exit(1)

# ── Discord client setup ──────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class SilverShadeBot(commands.Bot):
    """Custom Bot subclass so setup_hook runs before the bot connects."""

    async def setup_hook(self) -> None:
        # Attach shared services so cogs can access them via bot.api_client etc.
        self.api_client: ApiClient = api_client
        self.discord_manager: DiscordManager = discord_manager
        self.bot_config: Config = config

        await self.load_extension("cogs.admin_commands")
        await self.load_extension("cogs.general_commands")

        # Start the background polling task.
        asyncio.create_task(_polling_loop())


bot = SilverShadeBot(command_prefix=config.command_prefix, intents=intents)
api_client = ApiClient(config=config, logger=logger)
discord_manager = DiscordManager(
    bot=bot, config=config, api_client=api_client, logger=logger
)

# ── Events ────────────────────────────────────────────────────────────────────


@bot.event
async def on_ready() -> None:
    logger.info("Bot online as %s", bot.user)
    # Register slash commands to the configured guild for instant availability.
    try:
        guild = discord.Object(id=int(config.discord_guild_id))  # type: ignore[arg-type]
        synced = await bot.tree.sync(guild=guild)
        logger.info("Synced %d slash command(s) to guild.", len(synced))
    except Exception as exc:
        logger.warning("Slash command sync failed: %s", exc)
    await discord_manager.send_log("Admin bridge bot is online.")


# ── Background polling ────────────────────────────────────────────────────────

_poll_cursor: str | None = None
_poll_running: bool = False


async def _run_poll_tick() -> None:
    global _poll_cursor, _poll_running
    if _poll_running:
        return
    _poll_running = True
    try:
        payload = await api_client.poll_updates(_poll_cursor)
        sync_data = payload.get("data") or payload
        if isinstance(sync_data, dict) and sync_data.get("cursor"):
            _poll_cursor = sync_data["cursor"]
        await discord_manager.process_sync_payload(sync_data or {})
    except Exception as exc:
        logger.warning("Polling tick failed: %s", exc)
    finally:
        _poll_running = False


async def _polling_loop() -> None:
    await bot.wait_until_ready()
    while not bot.is_closed():
        await _run_poll_tick()
        await asyncio.sleep(config.poll_interval_seconds)


# ── Simulation mode (test helper) ─────────────────────────────────────────────


async def _run_simulation() -> None:
    if not config.admin_token:
        print(
            "ERROR: Missing SILVERSHADE_ADMIN_TOKEN for --simulate-discord-pickup",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        payload = await api_client.simulate_discord_pickup()
        sim = payload.get("data") or payload
        confirmed = int(
            sim.get("confirmedActions") or sim.get("confirmed") or sim.get("count") or 0
        )
        message = str(sim.get("message") or "")
        webhook_sent = sim.get("webhookSent") is True
        print(f"confirmed: {confirmed}")
        print(f"message: {message}")
        print(f"webhookSent: {webhook_sent}")
        if not webhook_sent:
            print("hint: backend needs DISCORD_TEST_WEBHOOK_URL set")
    finally:
        await api_client.close()


# ── Entry point ───────────────────────────────────────────────────────────────


async def _main() -> None:
    async with bot:
        await bot.start(config.discord_token)  # type: ignore[arg-type]


if __name__ == "__main__":
    if "--simulate-discord-pickup" in sys.argv:
        asyncio.run(_run_simulation())
    else:
        asyncio.run(_main())
