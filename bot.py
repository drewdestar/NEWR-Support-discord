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
from roles import is_staff, map_guild_roles  # noqa: E402

try:
    import memory as _brain  # noqa: E402
except Exception:  # pragma: no cover - brain optional at runtime
    _brain = None

COGS = ["cogs.support", "cogs.security", "cogs.moderation", "cogs.utility", "cogs.info", "cogs.dm", "cogs.community", "cogs.serverlog", "cogs.reportflow", "cogs.backup", "cogs.apply", "cogs.sticky", "cogs.deletelog"]
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


def _format_command_options(interaction: discord.Interaction) -> str:
    """Turn slash-command arguments into a readable detail string.

    User/channel/role arguments become tags (with their ID, so the
    target is identifiable even if they leave), strings/numbers are
    shown as-is, e.g.:
    user: @v.o.i.d.xyz (ID 144...), reason: hm
    Group/subcommand options are flattened recursively.
    """
    def fmt(opts) -> list[str]:
        out: list[str] = []
        for opt in opts or []:
            name = opt.get("name", "?")
            typ = opt.get("type")
            if typ in (1, 2):  # subcommand / subcommand group
                out.extend(fmt(opt.get("options")))
                continue
            val = opt.get("value")
            if typ == 6:  # user
                out.append(f"{name}: <@{val}> (ID {val})")
            elif typ == 7:  # channel
                out.append(f"{name}: <#{val}> (ID {val})")
            elif typ == 8:  # role
                out.append(f"{name}: <@&{val}> (ID {val})")
            else:
                out.append(f"{name}: {val}")
        return out
    try:
        data = interaction.data or {}
        return ", ".join(fmt(data.get("options")))
    except Exception:
        return ""


class RestrictedTree(discord.app_commands.CommandTree):
    """Global designated-channel rule for member commands.

    Commands stay VISIBLE to everyone in the command picker (nothing
    is hidden), but non-staff members may only USE them in their
    designated channel. Staff and top roles (is_staff) and the guild
    owner are exempt and may use any command anywhere, as are
    administrators.

    Designated channels (exact names in NEWR LABS):
      bot commands -> #🤖-bot-commands (default for member commands)
      /report      -> #⚠️-reports
      /suggest     -> #💡-suggestions
      /bug         -> #🐛-bug-reports
      /feedback    -> #📝-feedback
      /ticket_create -> #🎟️-ticket or #🤖-bot-commands
      /verify      -> #✔️-verification or #🤖-bot-commands
      ticket_*     -> inside a ticket-* channel, or #🎟️-ticket
    If none of a command's designated channels exists in the guild
    (e.g. a fresh restored server with different names), the rule
    fails open and the command is allowed anywhere, so members are
    never locked out by a missing channel.

    Enforcement (per member, rolling 24 hours, stored in
    command_offenses): 1st blocked attempt = ephemeral warning
    telling them the right channel. 2nd+ blocked attempt = automatic
    30-minute timeout + a #logs entry. The warning is sent from
    here, then False stops the command from running.
    """

    BOT_COMMANDS = "🤖-bot-commands"
    ALLOWED: dict[str, list[str]] = {
        "report": ["⚠️-reports"],
        "suggest": ["💡-suggestions"],
        "bug": ["🐛-bug-reports"],
        "feedback": ["📝-feedback"],
        "ticket_create": ["🎟️-ticket", "🤖-bot-commands"],
        "verify": ["✔️-verification", "🤖-bot-commands"],
    }

    def _qualified_name(self, interaction: discord.Interaction) -> str:
        data = interaction.data or {}
        parts = [data.get("name") or ""]
        opts = data.get("options") or []
        while opts:
            nxt = next((o for o in opts if o.get("type") in (1, 2)), None)
            if nxt is None:
                break
            parts.append(nxt.get("name") or "")
            opts = nxt.get("options") or []
        return " ".join(p for p in parts if p)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if guild is None:
            return True
        user = interaction.user
        if not isinstance(user, discord.Member):
            return True
        if guild.owner_id == user.id or user.guild_permissions.administrator:
            return True
        try:
            if is_staff(user):
                return True
        except Exception:
            pass
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return True
        qualified = self._qualified_name(interaction)
        top = qualified.split()[0] if qualified else ""
        # Ticket commands are allowed inside the ticket channel itself.
        if top.startswith("ticket_") and channel.name.startswith("ticket-"):
            return True
        allowed = self.ALLOWED.get(qualified) or self.ALLOWED.get(top) or [self.BOT_COMMANDS]
        guild_names = {c.name for c in guild.text_channels}
        if not (set(allowed) & guild_names):
            return True  # fail open: designated channel does not exist
        if channel.name in allowed:
            return True
        # Blocked: warn first, auto-mute on repeat within 24 hours.
        from datetime import datetime, timedelta
        now = datetime.now(timezone.utc)
        try:
            with db._conn() as conn:
                rows = conn.execute(
                    "SELECT created_at FROM command_offenses WHERE guild_id=? AND user_id=?",
                    (guild.id, user.id)).fetchall()
            recent = 0
            for r in rows:
                try:
                    dt = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if (now - dt).total_seconds() < 24 * 3600:
                        recent += 1
                except Exception:
                    pass
            with db._conn() as conn:
                conn.execute(
                    "INSERT INTO command_offenses (guild_id, user_id, command, channel_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (guild.id, user.id, qualified, channel.id, db.now()))
        except Exception:
            recent = 0
        dest = " or ".join(f"#{n}" for n in allowed)
        try:
            if recent == 0:
                await interaction.response.send_message(
                    f"⚠️ Bot commands must be used in their designated channel, not here.\n"
                    f"Please use `/{qualified}` in {dest}.\n"
                    f"If you keep using bot commands outside the designated channels, "
                    f"you will be muted automatically.",
                    ephemeral=True)
            else:
                try:
                    await user.timeout(timedelta(minutes=30),
                                       reason="Repeated bot commands outside designated channels after warning")
                except Exception:
                    pass
                await interaction.response.send_message(
                    f"🔇 You have been muted for 30 minutes for repeatedly using bot commands "
                    f"outside the designated channels after being warned.\n"
                    f"Please use `/{qualified}` in {dest} next time.",
                    ephemeral=True)
                try:
                    from cogs.modlog import log_action
                    await log_action(guild, "Muted", user, self.client.user,  # type: ignore[arg-type]
                                     "Repeated bot commands outside designated channels after warning",
                                     extra="Duration: 30 minutes (command channel violation)")
                except Exception:
                    pass
        except Exception:
            pass
        return False


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
                         tree_cls=RestrictedTree, **_proxy_kwargs())
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
            from cogs.support import (TicketCloseConfirmView, TicketCloseView,
                                      TicketCloseRequestView,
                                      TicketPanelCombinedView, TicketPanelView,
                                      TicketTypeView)
            from cogs.security import VerifyView
            from cogs.community import GiveawayJoinView, ReactionRoleView, RoleMenuSelectView
            from cogs.apply import ApplyPanelView, ApplyReviewView
            self.add_view(TicketPanelView())
            self.add_view(TicketTypeView())
            self.add_view(TicketPanelCombinedView())
            self.add_view(TicketCloseView())
            self.add_view(TicketCloseConfirmView())
            self.add_view(TicketCloseRequestView())
            self.add_view(VerifyView())
            self.add_view(GiveawayJoinView())
            self.add_view(ReactionRoleView())
            self.add_view(RoleMenuSelectView())
            self.add_view(ApplyPanelView())
            with db._conn() as conn:
                for row in conn.execute(
                        "SELECT id FROM applications WHERE status='open'"):
                    self.add_view(ApplyReviewView(row["id"]))
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

    async def on_app_command_completion(self, interaction: discord.Interaction,
                                      command: discord.app_commands.Command) -> None:
        """Staff command audit: every slash command a staff/high-role
        user runs in a guild is logged to #logs with tag, ID, roles,
        command, channel and WIB day/date/time. Non-staff commands are
        not logged, to keep the log readable. Failures here must never
        break the command itself, which has already completed."""
        try:
            if interaction.guild is None or not isinstance(interaction.user, discord.Member):
                return
            from roles import is_staff
            if not is_staff(interaction.user):
                return
            from cogs.modlog import log_staff_command
            await log_staff_command(interaction.guild, interaction.user,
                                    command.qualified_name, interaction.channel,  # type: ignore[arg-type]
                                    details=_format_command_options(interaction))
        except Exception as e:
            print(f"[audit] staff command log failed: {e}")

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
