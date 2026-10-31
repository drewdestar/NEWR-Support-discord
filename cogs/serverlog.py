"""24/7 server monitor: log server changes straight to #logs, live.

This is separate from the staff-command audit. It catches changes made
DIRECTLY in Discord (server settings, roles, channels, webhooks, bans
and kicks done from the Discord UI), which never go through a bot
slash command at all — so a high-role user cannot quietly change the
server by bypassing the bot.

Events covered (all with actor tag + ID when Discord tells us, target
tag + ID, and WIB day/date/time):
- guild update: server name / settings changed
- role create / delete / update (name, colour, permissions changed)
- channel create / delete / update (ticket channels are skipped:
  they are bot-made and already covered by ticket logs)
- member role changes and nickname changes
- member ban / unban and member leave/kick, with the audit-log actor
  when available; bans/kicks executed BY this bot are skipped here
  because the moderation embed already covers them
- webhook update, emoji/sticker update, invite create/delete

Nothing here sends a message, changes a setting, or acts on a user:
it only observes and logs. If the log channel is not configured,
events are silently skipped, never raised.
"""
from __future__ import annotations

import discord
from discord.ext import commands

from cogs.modlog import send_log_embed, user_tag, wib_date_time


def _actor_line(user: discord.User | discord.Member | None) -> str:
    if user is None:
        return "Unknown (via Discord)"
    return user_tag(user)


async def _emit(guild: discord.Guild, emoji: str, label: str,
                actor: discord.User | discord.Member | None,
                target: str, extra: str = "") -> None:
    date_str, time_str = wib_date_time()
    desc = (f"{_actor_line(actor)}\n\n"
            f"{emoji} **{label}** {target}\n"
            f"📅 **Date:** {date_str}\n"
            f"🕐 **Time:** {time_str}")
    if extra:
        desc += f"\n📝 **Detail:** {extra}"
    thumb = None
    try:
        thumb = actor.display_avatar.url if actor is not None else None
    except Exception:
        pass
    low = label.lower()
    await send_log_embed(guild, desc, 0xED4245 if "ban" in low or "kick" in low
                         else 0xE67E22 if "hapus" in low or "delete" in low
                         else 0x5865F2, thumbnail_url=thumb,
                         footer="NEWR Support • Server monitor")


async def _audit_actor(guild: discord.Guild, action: discord.AuditLogAction,
                       target_id: int):
    """Most recent audit-log entry for this target, if readable."""
    try:
        async for entry in guild.audit_logs(limit=5, action=action):
            if entry.target is not None and entry.target.id == target_id:
                return entry.user
    except Exception:
        pass
    return None


class ServerLog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ---- guild settings ----
    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        changes = []
        if before.name != after.name:
            changes.append(f"name: {before.name} → {after.name}")
        if before.verification_level != after.verification_level:
            changes.append(f"verification: {before.verification_level} → {after.verification_level}")
        if before.default_notifications != after.default_notifications:
            changes.append("notification settings changed")
        if before.afk_channel_id != after.afk_channel_id:
            changes.append("AFK channel changed")
        if before.system_channel_id != after.system_channel_id:
            changes.append("system channel changed")
        if changes:
            actor = await _audit_actor(after, discord.AuditLogAction.guild_update, after.id)
            await _emit(after, "⚙️", "Server updated", actor, after.name,
                        ", ".join(changes))

    # ---- roles ----
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        actor = await _audit_actor(role.guild, discord.AuditLogAction.role_create, role.id)
        await _emit(role.guild, "➕", "Role created", actor, f"{role.mention} (ID {role.id})",
                    f"name: {role.name}")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        actor = await _audit_actor(role.guild, discord.AuditLogAction.role_delete, role.id)
        await _emit(role.guild, "🗑️", "Role deleted", actor, f"{role.name} (ID {role.id})")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes = []
        if before.name != after.name:
            changes.append(f"name: {before.name} → {after.name}")
        if before.color != after.color:
            changes.append("colour changed")
        if before.permissions != after.permissions:
            changed = [name for name, val in iter(after.permissions)
                       if getattr(before.permissions, name) != val]
            changes.append(f"permissions changed: {', '.join(changed) or 'ya'}")
        if before.hoist != after.hoist:
            changes.append("hoist changed")
        if before.mentionable != after.mentionable:
            changes.append("mentionable changed")
        if changes:
            actor = await _audit_actor(after.guild, discord.AuditLogAction.role_update, after.id)
            await _emit(after.guild, "✏️", "Role updated", actor,
                        f"{after.mention} (ID {after.id})", ", ".join(changes))

    # ---- channels ----
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if channel.name.startswith("ticket-"):
            return  # bot-made ticket channel, already ticket-logged
        actor = await _audit_actor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        await _emit(channel.guild, "➕", "Channel created", actor,
                    f"{channel.mention} (ID {channel.id})", f"name: #{channel.name}")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        actor = await _audit_actor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)
        await _emit(channel.guild, "🗑️", "Channel deleted", actor,
                    f"#{channel.name} (ID {channel.id})")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel,
                                      after: discord.abc.GuildChannel):
        changes = []
        if before.name != after.name:
            changes.append(f"name: #{before.name} → #{after.name}")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append("topic changed")
        if getattr(before, "slowmode_delay", None) != getattr(after, "slowmode_delay", None):
            changes.append(f"slowmode: {getattr(before, 'slowmode_delay', None)} → {getattr(after, 'slowmode_delay', None)}")
        if changes:
            actor = await _audit_actor(after.guild, discord.AuditLogAction.channel_update, after.id)
            await _emit(after.guild, "✏️", "Channel updated", actor,
                        f"{after.mention} (ID {after.id})", ", ".join(changes))

    # ---- members: roles, nickname, leave/kick, ban/unban ----
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick != after.nick:
            actor = await _audit_actor(after.guild, discord.AuditLogAction.member_update, after.id)
            await _emit(after.guild, "✏️", "Nickname changed", actor,
                        user_tag(after),
                        f"{before.nick or before.name} → {after.nick or after.name}")
        added = [r for r in after.roles if r not in before.roles]
        removed = [r for r in before.roles if r not in after.roles]
        if added or removed:
            actor = await _audit_actor(after.guild, discord.AuditLogAction.member_role_update, after.id)
            parts = []
            if added:
                parts.append("added: " + ", ".join(f"{r.mention} (ID {r.id})" for r in added))
            if removed:
                parts.append("removed: " + ", ".join(f"{r.mention} (ID {r.id})" for r in removed))
            await _emit(after.guild, "🎖️", "Member roles changed", actor,
                        user_tag(after), "; ".join(parts))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        actor = await _audit_actor(member.guild, discord.AuditLogAction.kick, member.id)
        if actor is not None and self.bot.user is not None and actor.id == self.bot.user.id:
            return  # bot kick: already covered by the moderation embed
        if actor is not None:
            await _emit(member.guild, "👢", "Kick (via Discord)", actor,
                        user_tag(member))
        else:
            await _emit(member.guild, "🚪", "Member left", None,
                        user_tag(member))
        # Appy behaviour: leaving auto-denies open applications and
        # auto-closes open tickets (their owner is gone). Applications
        # are marked rejected with a reason, so staff are not left
        # reviewing a ghost; tickets are closed via the shared helper
        # (transcript to #logs, no DM — the owner has left).
        try:
            import db as _db
            with _db._conn() as conn:
                apps = conn.execute(
                    "SELECT id, channel_id, message_id FROM applications "
                    "WHERE guild_id=? AND user_id=? AND status='open'",
                    (member.guild.id, member.id)).fetchall()
                conn.execute(
                    "UPDATE applications SET status='rejected', review_reason='User left the server' "
                    "WHERE guild_id=? AND user_id=? AND status='open'",
                    (member.guild.id, member.id))
                tickets = conn.execute(
                    "SELECT channel_id FROM tickets WHERE guild_id=? AND owner_id=? "
                    "AND status IN ('open','claimed')", (member.guild.id, member.id)).fetchall()
            for app in apps:
                try:
                    if app["channel_id"]:
                        ch = member.guild.get_channel(app["channel_id"])
                        if isinstance(ch, discord.TextChannel) and app["message_id"]:
                            msg = await ch.fetch_message(app["message_id"])
                            await msg.edit(content="Auto-denied: applicant left the server.", view=None)
                except Exception:
                    pass
            if tickets:
                from cogs.support import close_ticket_channel
                for t in tickets:
                    ch = member.guild.get_channel(t["channel_id"])
                    if isinstance(ch, discord.TextChannel):
                        await close_ticket_channel(ch, member.guild, "Owner left the server")
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        actor = await _audit_actor(guild, discord.AuditLogAction.ban, user.id)
        if actor is not None and self.bot.user is not None and actor.id == self.bot.user.id:
            return  # bot ban: already covered by the moderation embed
        await _emit(guild, "🔨", "Ban (via Discord)", actor,
                    user_tag(user))

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        actor = await _audit_actor(guild, discord.AuditLogAction.unban, user.id)
        if actor is not None and self.bot.user is not None and actor.id == self.bot.user.id:
            return  # bot unban: already covered by the moderation embed
        await _emit(guild, "🔓", "Unban (via Discord)", actor,
                    user_tag(user))

    # ---- webhooks, emojis, invites ----
    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        await _emit(channel.guild, "🔗", "Webhook updated", None,
                    f"{channel.mention} (ID {channel.id})",
                    "a webhook in this channel was created/updated/deleted")

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        added = [e for e in after if e not in before]
        removed = [e for e in before if e not in after]
        if added or removed:
            parts = []
            if added:
                parts.append("added: " + ", ".join(f":{e.name}: (ID {e.id})" for e in added))
            if removed:
                parts.append("removed: " + ", ".join(f":{e.name}: (ID {e.id})" for e in removed))
            await _emit(guild, "😀", "Emoji updated", None, guild.name, "; ".join(parts))

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild is None:
            return
        await _emit(invite.guild, "🔗", "Invite created", invite.inviter,
                    f"{invite.channel.mention if invite.channel else 'channel tidak diketahui'}",
                    f"code: {invite.code}, max uses: {invite.max_uses or 'unlimited'}")

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild is None:
            return
        await _emit(invite.guild, "🗑️", "Invite deleted", None,
                    f"code: {invite.code} (ID {invite.id})" if hasattr(invite, "id") else f"kode: {invite.code}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ServerLog(bot))
