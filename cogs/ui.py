"""Shared NEWR Support UI — professional design system.

One branded look for every command, so the bot never looks like
a different bot from one command to the next:

- Colours by meaning, never at random:
  BLURPLE = panel / info, GREEN = success, RED = error / ban,
  YELLOW = warning / timeout, ORANGE = delete / kick, PURPLE = mute.
- Every embed has: a short emoji title, a footer
  "NEWR Support • NEWR LABS", and a timestamp. Professional
  embeds also get an author line ("NEWR Support") and, where the
  subject has one, a thumbnail (member avatar / guild icon).
- Structured data uses FIELDS, not one long description wall:
  e.g. a moderation action shows Target / Moderator / Reason /
  Duration as separate fields, so staff can scan it at a glance.
- Plain text is kept only where Discord needs it: pings in
  channel messages (a mention inside an embed does not ping),
  and long user-supplied text sent via /say. Everything a user
  reads as a bot reply is an embed.

Backwards-compatible: panel()/ok()/err()/warn()/info() keep
their old signatures, and every cog's emb() delegates to panel().
"""
from __future__ import annotations

from datetime import datetime, timezone

import discord

BLURPLE = 0x5865F2
GREEN = 0x57F287
RED = 0xED4245
YELLOW = 0xFEE75C
ORANGE = 0xE67E22
PURPLE = 0x9B59B6
GREY = 0x99AAB5

FOOTER = "NEWR Support • NEWR LABS"
AUTHOR = "NEWR Support"


def panel(title: str, description: str, color: int = BLURPLE) -> discord.Embed:
    """A branded panel embed: title, description, footer, timestamp.

    Stock Unicode emojis in bot-built text are translated to the
    NEWR custom emoji set (cogs.emoji) here, centrally, so every
    panel automatically uses custom emojis.
    """
    from cogs.emoji import translate
    embed = discord.Embed(title=translate(title), description=translate(description),
                          color=color, timestamp=datetime.now(timezone.utc))
    embed.set_footer(text=FOOTER)
    return embed


def make(title: str, description: str = "", color: int = BLURPLE,
         fields: list[tuple[str, str, bool]] | None = None,
         thumbnail: str | None = None, author_icon: str | None = None,
         author_name: str = AUTHOR) -> discord.Embed:
    """Full professional embed: author line, fields, thumbnail, footer.

    fields is a list of (name, value, inline). Empty values become
    "—" so a missing field never renders as a blank row.
    """
    from cogs.emoji import translate
    embed = discord.Embed(title=translate(title), description=translate(description) or None,
                          color=color, timestamp=datetime.now(timezone.utc))
    if author_name:
        embed.set_author(name=author_name, icon_url=author_icon)
    for name, value, inline in (fields or []):
        embed.add_field(name=translate(name), value=translate(value) or "—", inline=inline)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    embed.set_footer(text=FOOTER)
    return embed


def ok(title: str, description: str) -> discord.Embed:
    return panel(f"✅ {title}", description, GREEN)


def err(title: str, description: str) -> discord.Embed:
    return panel(f"❌ {title}", description, RED)


def warn(title: str, description: str) -> discord.Embed:
    return panel(f"⚠️ {title}", description, YELLOW)


def info(title: str, description: str) -> discord.Embed:
    return panel(f"ℹ️ {title}", description, BLURPLE)


def action(action_emoji: str, action_label: str, color: int,
           target: str, moderator: str,
           fields: list[tuple[str, str]] | None = None) -> discord.Embed:
    """A moderation / staff action card: Target + Moderator + details.

    Used by every moderation command reply, so a warn, mute, kick
    or ban all read the same way: who, by whom, and why — in
    fields, not in a single run-on sentence.
    """
    all_fields: list[tuple[str, str, bool]] = [
        ("👤 Target", target, True),
        ("🛡️ Moderator", moderator, True),
    ]
    for name, value in (fields or []):
        all_fields.append((name, value, False))
    return make(f"{action_emoji} {action_label}", color=color, fields=all_fields)


def denied() -> discord.Embed:
    """Standard staff-only denial, used by every staff-gated command."""
    return err("Staff Only", "This command can only be used by NEWR LABS staff and top roles.")
