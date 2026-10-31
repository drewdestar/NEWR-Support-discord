"""DM gate for NEWR Support.

Discord limitation, stated honestly: guild-synced slash commands only
appear inside the server, so DM support cannot be a slash command run
in a DM. DM support therefore works via direct messages (on_message),
while /dm-access (a guild slash command) lets a user check their
DM-access status from inside the server.

Gate (runtime role-name lookup, never hardcoded role IDs):
- Staff / top roles ONLY may chat privately with the bot for support:
  FOUNDER, 👑 Founder, NEWR, 🏛️ Executive, ⭐ Admin, 🛡️ Senior Mod,
  ⚔️ Moderator, 🎯 Team Lead, 🤝 Helper, Security (see roles.py:
  DM_STAFF_ROLE_NAMES, plus the guild owner).
- Regular members (Verified Member, VIP, Elite, Creator, etc.) and
  non-members must NOT get DM support. They get one polite denial
  per burst (10-minute cooldown, to avoid reply-spam) directing them
  to /ticket_create in the NEWR LABS server, and their message is
  NOT stored as a support request.

Staff DM flow:
- "menu" / "help" in DM -> staff DM menu.
- Any other DM text -> stored as a DM support request in SQLite
  (dm_requests table), a summary is forwarded to LOG_CHANNEL_ID
  when set, and the staff member gets a confirmation with the
  request ID. Follow-up in the server is via /ticket_create or by
  sending another DM, which creates another request.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import db
import smart
from roles import DM_STAFF_ROLE_NAMES, dm_staff_roles, is_dm_staff

def _env_int(name: str):
    try:
        return int(os.environ[name]) if os.environ.get(name) else None
    except ValueError:
        return None


NEWR_LABS_GUILD_ID = _env_int("GUILD_ID")
LOG_CHANNEL_ID = _env_int("LOG_CHANNEL_ID")
_DENIAL_COOLDOWN_SECONDS = 600  # one denial per user per burst

STAFF_MENU = (
    "👋 Hello, NEWR LABS staff! You have DM support access.\n\n"
    "**DM Staff Menu — NEWR Support**\n"
    "• Send any message in this DM to create a new support request.\n"
    "  The request is saved and forwarded to the staff log channel if one is set.\n"
    "• Type `menu` to see this menu again.\n"
    "• For a full ticket in the server, use `/ticket_create` in NEWR LABS.\n"
    "• Check your DM access anytime from the server with `/dm-access`."
)

MEMBER_DENIAL = (
    "Hello! Sorry, NEWR Support DM support is only for staff and the "
    "top NEWR LABS roles, so this DM cannot be processed as a "
    "support request.\n\n"
    "If you are a member, please use `/ticket_create` in the NEWR LABS server, "
    "staff will help you there. Thanks for reaching out!"
)

NON_MEMBER_DENIAL = (
    "Hello! Sorry, NEWR Support DM support is only for staff and the "
    "top NEWR LABS roles. You are not registered as a NEWR LABS member, "
    "so this DM cannot be processed.\n\n"
    "Please join the NEWR LABS server first, then use `/ticket_create` in "
    "the server if you need help. Thanks!"
)


def _resolve_guild(bot: commands.Bot, fallback: discord.Guild | None = None) -> discord.Guild | None:
    if NEWR_LABS_GUILD_ID:
        guild = bot.get_guild(NEWR_LABS_GUILD_ID)
        if guild is not None:
            return guild
        # Fail closed: never fall back to an arbitrary other server for
        # a DM staff check when the target guild is not visible.
        return fallback if fallback is not None and fallback.id == NEWR_LABS_GUILD_ID else None
    if fallback is not None:
        return fallback
    return None


async def _resolve_member(bot: commands.Bot, user_id: int,
                          fallback_guild: discord.Guild | None = None) -> tuple[discord.Guild | None, discord.Member | None]:
    guild = _resolve_guild(bot, fallback_guild)
    if guild is None:
        return None, None
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            member = None
    return guild, member


class DMGate(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._denied_at: dict[int, float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # DM only: guild messages are handled by the other cogs.
        if message.author.bot or message.guild is not None:
            return
        # A DM application owns the DM while it is in progress: each
        # answer (position, experience, reason, availability) is an
        # application answer, NOT a support request. Without this
        # guard, one DM application spams #logs with one support
        # request per answer, plus a "saved as #N" reply per answer.
        with db._conn() as conn:
            in_application = conn.execute(
                "SELECT 1 FROM dm_applications WHERE user_id=? LIMIT 1",
                (message.author.id,)).fetchone() is not None
        if in_application:
            return
        user = message.author
        guild, member = await _resolve_member(self.bot, user.id)
        if guild is None:
            await message.channel.send(
                "Sorry, the bot is not connected to the NEWR LABS server yet, so DM "
                "access cannot be verified. Please use /ticket_create in the NEWR LABS server.")
            return
        if member is None or not is_dm_staff(member):
            # One denial per burst: reply once, then ignore repeats for
            # 10 minutes so a member cannot spam the bot into replying.
            now = time.time()
            if now - self._denied_at.get(user.id, 0) < _DENIAL_COOLDOWN_SECONDS:
                return
            self._denied_at[user.id] = now
            await message.channel.send(NON_MEMBER_DENIAL if member is None else MEMBER_DENIAL)
            return

        # Staff / top roles only, from here on.
        text = (message.content or "").strip()
        if not text or text.lower() in ("menu", "help", "halo", "hi", "hello"):
            tip = smart.daily_tip()
            from cogs.ui import make as _make
            await message.channel.send(embed=_make("👋 NEWR LABS Staff — DM Menu",
                "You have DM support access.",
                fields=[("📩 New Request", "Send any message in this DM to create a support request.", False),
                        ("🎟️ Full Ticket", "Use `/ticket_create` in NEWR LABS for a full ticket.", False),
                        ("🔁 Menu", "Type `menu` to see this menu again.", False),
                        (f"💡 Tip of the day — {tip['category']}", tip['text'], False)]))
            return
        # Staff-only smart tip in DM (on_message): "tip"/"tips" returns the
        # rotating local tip instead of being stored as a support request.
        if text.lower() in ("tip", "tips", "tips please", "smart tip"):
            tip = smart.daily_tip()
            await message.channel.send(f"💡 Tip of the day ({tip['category']}): {tip['text']}")
            return
        # Staff DM support request: store it, forward a summary to the
        # log channel when configured, confirm with the request ID.
        request_id = db.add_row(
            "dm_requests", guild_id=guild.id, user_id=user.id,
            text=text[:2000], status="open", created_at=db.now())
        if LOG_CHANNEL_ID:
            channel = guild.get_channel(LOG_CHANNEL_ID)
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(
                        f"📩 **DM support request #{request_id}** from {user.mention} "
                        f"({user}, staff roles: {', '.join(r.name for r in dm_staff_roles(member))})\n"
                        f"> {text[:1000]}")
                except discord.HTTPException:
                    pass
        await message.channel.send(
            f"✅ Your DM support request has been saved as **#{request_id}**.\n"
            f"{smart.triage_text(text)}\n"
            f"Staff can follow up from the log channel, or you can open a full ticket "
            f"in the server with `/ticket_create`. Send another message in this DM for a new request, "
            f"or type `menu` for the staff menu.")

    @app_commands.command(name="dm-access", description="Check whether you have staff DM access to NEWR Support")
    async def dm_access(self, interaction: discord.Interaction):
        # Slash commands do not run in DMs (guild-synced), so this is
        # expected to run inside a server; handle a DM invocation anyway.
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command can only be checked from inside the server. DM support itself "
                "runs via DM messages (not a slash command in DM) — see the README.",
                ephemeral=True)
            return
        _, member = await _resolve_member(
            self.bot, interaction.user.id, fallback_guild=interaction.guild)
        if member is None:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="DM Access: Non-member",
                    description=("You are not registered as a NEWR LABS member, so you "
                                 "do not have DM support access. Join the NEWR LABS server first, "
                                 "then use /ticket_create in the server if you need help."),
                    color=0xED4245, timestamp=datetime.now(timezone.utc)),
                ephemeral=True)
            return
        staff_roles = dm_staff_roles(member)
        if is_dm_staff(member):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="DM Access: Staff ✅",
                    description=("You have NEWR Support DM support access.\n"
                                 f"Your staff/top roles: {', '.join(r.name for r in staff_roles) or 'guild owner'}\n"
                                 "DM this bot to create a support request, or type `menu` in DM."),
                    color=0x57F287, timestamp=datetime.now(timezone.utc)),
                ephemeral=True)
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="DM Access: Member only",
                description=("NEWR Support DM support is only for staff and the top roles "
                             "(FOUNDER, 👑 Founder, NEWR, 🏛️ Executive, ⭐ Admin, 🛡️ Senior Mod, "
                             "⚔️ Moderator, 🎯 Team Lead, 🤝 Helper, Security).\n"
                             "As a member, please use /ticket_create in the NEWR LABS server."),
                color=0xFEE75C, timestamp=datetime.now(timezone.utc)),
            ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DMGate(bot))
