"""YAGPDB-style moderation log embeds, sent to the #logs channel.

Style copied from the YAGPDB screenshot the user shared:
- the bot itself is the message author (like YAGPDB.xyz APP)
- a coloured left border (embed colour): red for bans, orange for kicks,
  yellow for warns, purple for timeouts/mutes, green for unbans/unmutes
- first line: the moderator, with their Discord ID
- action line: emoji + bold action + target, with their Discord ID
- reason line: document emoji + bold "Reason:" + reason
- the target's avatar as the embed thumbnail, on the right
- embed timestamp = when the action happened

Log channel resolution: LOG_CHANNEL_ID from the environment first
(the channel the user pointed at, #logs), falling back to the
`log_channel` DB setting. If neither is set, logging is skipped
silently — moderation itself must never fail because logging did.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord

import db


def _env_int(name: str) -> int | None:
    try:
        return int(os.environ[name]) if os.environ.get(name) else None
    except ValueError:
        return None


async def log_channel(guild: discord.Guild) -> discord.TextChannel | None:
    log_id = _env_int("LOG_CHANNEL_ID")
    if not log_id:
        raw = db.get_setting(guild.id, "log_channel", "")
        log_id = int(raw) if raw.isdigit() else None
    if not log_id:
        return None
    channel = guild.get_channel(log_id)
    return channel if isinstance(channel, discord.TextChannel) else None


# action -> (emoji, past-tense label, colour)
ACTIONS: dict[str, tuple[str, str, int]] = {
    "Banned": ("🔨", "Banned", 0xED4245),
    "Unbanned": ("🔓", "Unbanned", 0x57F287),
    "Kicked": ("👢", "Kicked", 0xE67E22),
    "Warned": ("⚠️", "Warned", 0xFEE75C),
    "Muted": ("🔇", "Muted", 0x5865F2),
    "Unmuted": ("🔊", "Unmuted", 0x57F287),
    "Timed out": ("⏱️", "Timed out", 0x5865F2),
    "Joined": ("👋", "Joined", 0x57F287),
    "Warnings cleared": ("🧹", "Warnings cleared", 0x57F287),
}


def user_tag(user) -> str:
    """Clickable mention + plain username + explicit ID, all three.

    History: v1 (mention + plain name) rendered the pill as a
    raw ID on the user's client (2026-10-31 17:56 WIB screenshot);
    v2 (plain @username only, 17:58 WIB) fixed the rendering but
    the user then complained (20:19 WIB screenshot) that the ID
    was gone and the username could not be tapped. v3 keeps all
    three pieces as text, so no client rendering quirk can hide
    any of them: the pill stays tappable to open the profile,
    the username is readable as plain text even if the pill
    renders as an ID, and the ID is readable as plain text too.
    """
    try:
        name = getattr(user, "name", None) or getattr(user, "display_name", None)
    except Exception:
        name = None
    try:
        uid = user.id
    except Exception:
        uid = None
    if name and uid is not None:
        return f"{user.mention} (@{name} — ID {uid})"
    if name:
        return f"@{name}"
    if uid is not None:
        return f"ID {uid}"
    return "Unknown"


async def log_action(guild: discord.Guild, action: str,
                     target: discord.User | discord.Member,
                     moderator: discord.User | discord.Member | None,
                     reason: str, extra: str = "") -> bool:
    """Send one YAGPDB-style embed to the log channel. Returns True if sent."""
    channel = await log_channel(guild)
    if channel is None:
        return False
    emoji, label, colour = ACTIONS.get(action, ("📝", action, 0x5865F2))
    # Log tags are mention + @username + ID (see user_tag).
    mod_line = (user_tag(moderator) if moderator is not None else "System")
    desc = (f"{mod_line}\n\n"
            f"{emoji} **{label}** {user_tag(target)}\n"
            f"📄 **Reason:** {reason}")
    if extra:
        desc += f"\n{extra}"
    embed = discord.Embed(description=desc, color=colour,
                          timestamp=datetime.now(timezone.utc))
    try:
        avatar = target.display_avatar.url
    except Exception:
        avatar = None
    if avatar:
        embed.set_thumbnail(url=avatar)
    embed.set_footer(text="NEWR Support • NEWR LABS")
    try:
        await channel.send(embed=embed)
        return True
    except discord.HTTPException:
        return False


# Indonesian day/month names for the audit log (user asked for
# "tanggal apa, hari apa" in the log, in WIB, not UTC).
_WIB = ZoneInfo("Asia/Jakarta")
_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = ["", "January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


async def log_staff_command(guild: discord.Guild, user: discord.Member,
                            command_name: str,
                            channel: discord.abc.GuildChannel | None,
                            details: str = "") -> bool:
    """Audit log: one embed per slash command used by a staff member.

    Shows the user as a tag + ID, their staff roles, the exact command,
    the channel it was run in, and the WIB day/date/time, so any
    misuse by a high-role user is traceable after the fact.
    """
    target = await log_channel(guild)
    if target is None:
        return False
    date_str, time_str = wib_date_time()
    try:
        from roles import staff_roles
        held = [r.name for r in user.roles
                if r.id in {r.id for r in staff_roles(guild)}]
    except Exception:
        held = []
    roles_line = ", ".join(held) if held else "Staff"
    desc = (f"{user_tag(user)}\n\n"
            f"🎖️ **Role:** {roles_line}\n"
            f"📋 **Command:** /{command_name}\n"
            f"📍 **Channel:** {channel.mention if channel is not None else '-'}\n"
            f"📅 **Date:** {date_str}\n"
            f"🕐 **Time:** {time_str}")
    if details:
        desc += f"\n📝 **Detail:** {details}"
    embed = discord.Embed(description=desc, color=0x5865F2,
                          timestamp=datetime.now(timezone.utc))
    try:
        embed.set_thumbnail(url=user.display_avatar.url)
    except Exception:
        pass
    embed.set_footer(text="NEWR Support • Staff command audit")
    try:
        await target.send(embed=embed)
        return True
    except discord.HTTPException:
        return False


async def send_log_embed(guild: discord.Guild, desc: str, colour: int,
                         thumbnail_url: str | None = None,
                         footer: str = "NEWR Support") -> bool:
    """Send any pre-formatted log embed to the log channel."""
    channel = await log_channel(guild)
    if channel is None:
        return False
    embed = discord.Embed(description=desc, color=colour,
                          timestamp=datetime.now(timezone.utc))
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    embed.set_footer(text=footer)
    try:
        await channel.send(embed=embed)
        return True
    except discord.HTTPException:
        return False


def wib_date_time() -> tuple[str, str]:
    """(day/date, time) in WIB, e.g. ('Jumat, 30 Oktober 2026', '23:56 WIB')."""
    now = datetime.now(_WIB)
    return (f"{_DAYS[now.weekday()]}, {now.day} {_MONTHS[now.month]} {now.year}",
            now.strftime("%H:%M") + " WIB")
