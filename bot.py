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
from pathlib import Path

import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv  # optional, only if installed
    load_dotenv()
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Shared brain: ONE memory.db for both bots. The module lives in
# ../shared-brain/ next to this bot directory (and in the VM at
# ~/workspace/bots/shared-brain/). If it cannot be found, the bot
# still runs; brain features are simply disabled, never fatal.
_BRAIN_DIRS = [
    Path(__file__).resolve().parent.parent / "shared-brain",
    Path.home() / "workspace" / "bots" / "shared-brain",
]
for _d in _BRAIN_DIRS:
    if (_d / "memory.py").exists():
        sys.path.insert(0, str(_d))
        break

import db  # noqa: E402
from roles import map_guild_roles  # noqa: E402

try:
    import memory as _brain  # noqa: E402
except Exception:  # pragma: no cover - brain optional at runtime
    _brain = None

COGS = ["cogs.support", "cogs.security", "cogs.moderation", "cogs.utility", "cogs.info", "cogs.dm"]
try:
    GUILD_ID = int(os.environ["GUILD_ID"]) if os.environ.get("GUILD_ID") else None
except ValueError:
    GUILD_ID = None


def _proxy_kwargs() -> dict:
    """VM egress goes through an HTTP proxy; direct TLS to Discord fails
    here (SSL WRONG_VERSION_NUMBER), while aiohttp with trust_env works.
    discord.py does not read proxy env vars itself, so pass them explicitly.
    Credentials stay in the environment, never in code or logs."""
    from urllib.parse import unquote, urlparse

    raw = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
    if not raw:
        return {}
    parsed = urlparse(raw)
    proxy = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or 3128}"
    kwargs: dict = {"proxy": proxy}
    if parsed.username:
        import aiohttp

        kwargs["proxy_auth"] = aiohttp.BasicAuth(
            unquote(parsed.username),
            unquote(parsed.password or ""))
    return kwargs


class SupportBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True  # privileged: enable in Developer Portal
        intents.messages = True
        intents.dm_messages = True  # needed for the staff-only DM gate
        intents.message_content = True  # privileged: needed for anti-spam/link and DM text
        intents.voice_states = True
        super().__init__(command_prefix=None, intents=intents, help_command=None,
                         **_proxy_kwargs())
        self.started_at = datetime.now(timezone.utc)

    async def setup_hook(self) -> None:
        db.init_db()
        self.shared_brain_path = None
        self.brain_available = False
        if _brain is not None:
            try:
                raw = os.environ.get("SHARED_BRAIN_DB") or None
                self.shared_brain_path = _brain.init_memory(
                    os.path.expanduser(os.path.expandvars(raw)) if raw else None)
                self.brain_available = True
                print(f"[brain] shared memory: {self.shared_brain_path}")
            except Exception as e:
                print(f"[brain] disabled: {e}")
        for cog in COGS:
            await self.load_extension(cog)
        # Persistent views: without this, ticket/verify buttons posted
        # before a restart become dead after restart. Both views use
        # stable custom_ids, so re-registering them here revives old
        # messages as well as new ones.
        try:
            from cogs.support import TicketPanelView
            from cogs.security import VerifyView
            self.add_view(TicketPanelView())
            self.add_view(VerifyView())
        except Exception as e:
            print(f"[views] persistent view registration failed: {e}")
        self._brain_task = asyncio.create_task(self._brain_inbox_loop())

    async def _brain_inbox_loop(self) -> None:
        """Poll the shared brain every 45s for messages to newr-support.

        Each message is handled exactly once and marked done in a
        finally block (poison messages must not loop forever). This
        bot NEVER replies to a bot_message with a new bot_message of
        the same kind, so Support <-> AI cannot ping-pong.
        """
        await self.wait_until_ready()
        while not self.is_closed():
            if self.brain_available and _brain is not None:
                try:
                    for msg in _brain.fetch_bot_messages("newr-support"):
                        try:
                            if msg.get("kind") == "ai_summary":
                                _brain.remember_event(
                                    msg.get("guild_id"), "ai_summary_received",
                                    user_id=msg.get("user_id"),
                                    details=(msg.get("text") or "")[:500],
                                    source_bot="newr-support")
                            log_id = os.environ.get("LOG_CHANNEL_ID")
                            if log_id:
                                ch = self.get_channel(int(log_id))
                                if ch is not None:
                                    await ch.send(
                                        f"[brain] from {msg.get('from_bot')}: "
                                        f"{msg.get('kind')} (user {msg.get('user_id')})")
                            print(f"[brain] inbox {msg.get('from_bot')} -> "
                                  f"newr-support kind={msg.get('kind')} id={msg.get('id')}")
                        except Exception as e:
                            print(f"[brain] inbox handling failed: {e}")
                        finally:
                            try:
                                _brain.mark_bot_message_done(msg["id"])
                            except Exception:
                                pass
                except Exception as e:
                    print(f"[brain] inbox poll failed: {e}")
            await asyncio.sleep(45)

    async def on_ready(self) -> None:
        print(f"Logged in as {self.user} (id={self.user.id})")
        if getattr(self, "_synced", False):
            return
        self._synced = True
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
