"""Message delete / edit log, split in two staff channels.

Two channels, both in Leadership and both staff-only (the split is
by WHOSE deletion it is, not by who may read it — deleted content
must never be visible to regular members):

1. #deleted-messages — ordinary deletions: a member deletes their
   own or someone else's message via Discord, and edits. This is
   the "pesan yang dihapus" channel.
2. #staff-deletions — high-role deletions, kept separate so staff
   actions are easy to audit on their own:
   - a staff member deletes a message via Discord (audit-log
     deleter holds a staff role, or is the guild owner), and
   - a deletion executed by this bot via a staff command
     (purge, ticket close, etc. — audit actor is the bot, which
     only acts on a staff command). These used to be skipped
     entirely; now they go here instead, with a note that the
     moderator is in #logs, so nothing is hidden.

Routing rule, in order:
- Deletion by the bot -> #staff-deletions ("via bot command").
- Deletion by a staff member (audit log) -> #staff-deletions.
- Deletion by anyone else, or deleter unknown -> #deleted-messages.
  Unknown defaults to #deleted-messages, because most deletions
  are members deleting their own messages and Discord does not
  always supply an audit entry (e.g. self-deletes have no
  message_delete audit entry at all).
- Edits are routed by the EDITOR: staff author -> #staff-deletions,
  member author -> #deleted-messages.
- Bulk deletes: audit actor staff/bot -> #staff-deletions, else
  #deleted-messages.

What is NOT logged:
- Deletions/edits inside either log channel itself, or #logs.
- Messages from bot accounts (their content is covered by
  ticket / panel logs where it matters).
- DMs: server log only.

Honest limit: Discord only sends deleted content if the bot had
that message in its in-memory cache at delete time. Messages
sent before the last bot restart, or very old messages, log as
"content unavailable" — the deletion itself is still recorded.
"""
from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord.ext import commands

import db
from cogs.modlog import user_tag, wib_date_time
from roles import is_staff


async def _channel_by_setting(guild: discord.Guild, setting: str, fallback_name: str) -> discord.TextChannel | None:
    raw = db.get_setting(guild.id, setting, "")
    if raw and raw.isdigit():
        ch = guild.get_channel(int(raw))
        if isinstance(ch, discord.TextChannel):
            return ch
    ch = discord.utils.get(guild.text_channels, name=fallback_name)
    return ch if isinstance(ch, discord.TextChannel) else None


async def _member_channel(guild: discord.Guild) -> discord.TextChannel | None:
    return await _channel_by_setting(guild, "deleted_log_channel", "deleted-messages")


async def _staff_channel(guild: discord.Guild) -> discord.TextChannel | None:
    return await _channel_by_setting(guild, "staff_deleted_log_channel", "staff-deletions")


async def _is_log_channel(guild: discord.Guild, channel_id: int) -> bool:
    for ch in (await _member_channel(guild), await _staff_channel(guild)):
        if ch is not None and ch.id == channel_id:
            return True
    return False


async def _audit_actor(guild: discord.Guild, action: discord.AuditLogAction):
    """Most recent audit-log user for this action, if readable."""
    try:
        async for entry in guild.audit_logs(limit=5, action=action):
            if entry.user is not None:
                return entry.user
    except Exception:
        pass
    return None


async def _is_staff_user(guild: discord.Guild, user: discord.User | discord.Member | None) -> bool:
    if user is None:
        return False
    if guild.owner_id == user.id:
        return True
    member = guild.get_member(user.id)
    if member is None:
        try:
            member = await guild.fetch_member(user.id)
        except Exception:
            return False
    if member is None:
        return False
    try:
        return is_staff(member)
    except Exception:
        return False


def _embed(title: str, description: str, color: int, author=None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color,
                          timestamp=datetime.now(timezone.utc))
    embed.set_footer(text="NEWR Support • Message log")
    if author is not None:
        try:
            embed.set_thumbnail(url=author.display_avatar.url)
        except Exception:
            pass
    return embed


class DeleteLog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _send(self, guild: discord.Guild, embed: discord.Embed, staff: bool) -> None:
        channel = await _staff_channel(guild) if staff else await _member_channel(guild)
        if channel is None:
            # Fall back to the other channel rather than dropping the log.
            channel = await _member_channel(guild) if staff else await _staff_channel(guild)
        if channel is None:
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        if await _is_log_channel(guild, payload.channel_id):
            return
        cached = payload.cached_message
        if cached is not None and cached.author.bot:
            return
        deleter = None
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.message_delete):
                if entry.extra is not None and getattr(entry.extra, "channel", None) is not None:
                    if entry.extra.channel.id == payload.channel_id:
                        deleter = entry.user
                        break
        except Exception:
            deleter = None
        via_bot = deleter is not None and self.bot.user is not None and deleter.id == self.bot.user.id
        staff = via_bot or await _is_staff_user(guild, deleter)
        deleter_text = ("via bot command (moderator in #logs)" if via_bot
                        else user_tag(deleter) if deleter else "Unknown (via Discord)")
        channel = guild.get_channel(payload.channel_id)
        ch_text = channel.mention if isinstance(channel, discord.TextChannel) else f"channel ID {payload.channel_id}"
        date_str, time_str = wib_date_time()
        if cached is not None:
            author = cached.author
            content = cached.content or "(no text — attachment/embed only)"
            if len(content) > 1500:
                content = content[:1500] + "… (truncated)"
            attachments = "\n".join(f"• {a.filename} ({a.url})" for a in cached.attachments) or "—"
            desc = (f"**Author:** {user_tag(author)}\n"
                    f"**Channel:** {ch_text}\n"
                    f"**Deleted by:** {deleter_text}\n"
                    f"📅 **Date:** {date_str}  🕐 **Time:** {time_str}\n\n"
                    f"**Content:**\n{content}\n\n"
                    f"**Attachments:**\n{attachments}\n\n"
                    f"Message ID: {payload.message_id}")
            await self._send(guild, _embed("🗑️ Message Deleted", desc, 0xED4245, author), staff)
        else:
            desc = (f"**Channel:** {ch_text}\n"
                    f"**Deleted by:** {deleter_text}\n"
                    f"📅 **Date:** {date_str}  🕐 **Time:** {time_str}\n\n"
                    f"⚠️ Content unavailable — this message was not in the bot's cache "
                    f"(sent before the last restart, or too old). The deletion itself is still recorded.\n\n"
                    f"Message ID: {payload.message_id}")
            await self._send(guild, _embed("🗑️ Message Deleted (content unavailable)", desc, 0xE67E22), staff)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        if payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild is None:
            return
        if await _is_log_channel(guild, payload.channel_id):
            return
        actor = await _audit_actor(guild, discord.AuditLogAction.message_bulk_delete)
        via_bot = actor is not None and self.bot.user is not None and actor.id == self.bot.user.id
        staff = via_bot or await _is_staff_user(guild, actor)
        channel = guild.get_channel(payload.channel_id)
        ch_text = channel.mention if isinstance(channel, discord.TextChannel) else f"channel ID {payload.channel_id}"
        date_str, time_str = wib_date_time()
        ids = "\n".join(str(mid) for mid in list(payload.message_ids)[:50])
        if len(payload.message_ids) > 50:
            ids += f"\n… and {len(payload.message_ids) - 50} more"
        actor_text = ("via bot command (moderator in #logs)" if via_bot
                      else user_tag(actor) if actor else "Unknown (via Discord)")
        desc = (f"**Channel:** {ch_text}\n"
                f"**Deleted by:** {actor_text}\n"
                f"📅 **Date:** {date_str}  🕐 **Time:** {time_str}\n\n"
                f"**{len(payload.message_ids)} message(s) bulk-deleted.** Discord does not supply "
                f"individual contents for bulk deletes.\n\n"
                f"**Message IDs:**\n{ids}")
        await self._send(guild, _embed("🧹 Messages Bulk-Deleted", desc, 0xE67E22), staff)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild is None or before.author.bot:
            return
        if before.content == after.content:
            return  # embed-only change, not a text edit
        if await _is_log_channel(before.guild, before.channel.id):
            return
        staff = await _is_staff_user(before.guild, before.author)
        date_str, time_str = wib_date_time()
        old = before.content or "(no text)"
        new = after.content or "(no text)"
        if len(old) > 800:
            old = old[:800] + "… (truncated)"
        if len(new) > 800:
            new = new[:800] + "… (truncated)"
        desc = (f"**Author:** {user_tag(before.author)}\n"
                f"**Channel:** {before.channel.mention}\n"
                f"📅 **Date:** {date_str}  🕐 **Time:** {time_str}\n\n"
                f"**Before:**\n{old}\n\n"
                f"**After:**\n{new}\n\n"
                f"[Jump to message]({after.jump_url})")
        await self._send(before.guild, _embed("✏️ Message Edited", desc, 0xFEE75C, before.author), staff)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DeleteLog(bot))
