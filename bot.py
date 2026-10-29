"""NEWR Support bot entrypoint. Config comes only from environment variables.

Required: DISCORD_TOKEN, GUILD_ID (guild commands sync target).
Optional: LOG_CHANNEL_ID, SUPPORT_CATEGORY_ID, DB_PATH.
Run:  pip install -r requirements.txt && python3 bot.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv  # optional, only if installed
    load_dotenv()
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db  # noqa: E402
from roles import map_guild_roles  # noqa: E402

COGS = ["cogs.support", "cogs.security", "cogs.moderation", "cogs.utility", "cogs.info", "cogs.dm"]
GUILD_ID = int(os.environ["GUILD_ID"]) if os.environ.get("GUILD_ID") else None


class SupportBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True  # privileged: enable in Developer Portal
        intents.messages = True
        intents.dm_messages = True  # needed for the staff-only DM gate
        intents.message_content = True  # privileged: needed for anti-spam/link and DM text
        intents.voice_states = True
        super().__init__(command_prefix=None, intents=intents, help_command=None)
        self.started_at = datetime.now(timezone.utc)

    async def setup_hook(self) -> None:
        db.init_db()
        for cog in COGS:
            await self.load_extension(cog)

    async def on_ready(self) -> None:
        print(f"Logged in as {self.user} (id={self.user.id})")
        for guild in self.guilds:
            mapping = map_guild_roles(guild)
            summary = ", ".join(f"{k}:{len(v)}" for k, v in mapping.items() if v)
            print(f"[roles] {guild.name}: {summary}")
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"Synced {len(synced)} slash commands to guild {GUILD_ID}")
        else:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash commands globally")

    async def on_guild_join(self, guild: discord.Guild) -> None:
        mapping = map_guild_roles(guild)
        print(f"[roles] Joined {guild.name}: " +
              ", ".join(f"{k}:{len(v)}" for k, v in mapping.items() if v))


def main() -> None:
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is not set. See .env.example.")
    asyncio.run(SupportBot().start(token))


if __name__ == "__main__":
    main()
