"""Moderation cog: warns, timeouts, kicks, bans, purges, roles, nicknames."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

import db
from cogs.modlog import log_action
from cogs.ui import action as _action, denied as _denied
from roles import is_staff

EMBED_COLOR = 0xFEE75C


def emb(title: str, desc: str) -> discord.Embed:
    from cogs.ui import panel
    return panel(title, desc, EMBED_COLOR)


def staff_only(i: discord.Interaction) -> bool:
    return is_staff(i.user)  # type: ignore[arg-type]


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="warn", description="Warn a member (staff)")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        # Same ladder as report buttons: Warn 1/2/3 roles, DM appeal,
        # and Warn 3 auto-mutes 24 jam (see cogs.reportflow.apply_warn).
        from cogs.reportflow import apply_warn
        level, wid, _ = await apply_warn(interaction.guild, member.id,
                                         interaction.user, reason)
        await interaction.response.send_message(embed=_action("⚠️", f"Warned — Warn {level} (#{wid})", 0xFEE75C, f"{member.mention} (ID {member.id})", interaction.user.mention, [("📄 Reason", reason)] + ([("⏱️ Note", "Auto-muted for 24 hours (Warn 3).")] if level >= 3 else [])))

    @app_commands.command(name="warns", description="List warnings for a member")
    async def warns(self, interaction: discord.Interaction, member: discord.Member):
        with db._conn() as conn:
            rows = conn.execute("SELECT * FROM warns WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 20",
                                (interaction.guild.id, member.id)).fetchall()
        text = "\n".join(f"#{r['id']} by <@{r['moderator_id']}>: {r['reason']}" for r in rows) or "No warnings."
        await interaction.response.send_message(embed=emb(f"Warnings for {member}", text), ephemeral=True)

    @app_commands.command(name="clear_warns", description="Clear all warnings for a member (staff)")
    async def clear_warns(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            conn.execute("DELETE FROM warns WHERE guild_id=? AND user_id=?", (interaction.guild.id, member.id))
        await interaction.response.send_message(embed=_action("🧹", "Warnings Cleared", 0x57F287, f"{member.mention} (ID {member.id})", interaction.user.mention))
        await log_action(interaction.guild, "Warnings cleared", member, interaction.user, "Warnings cleared")

    @app_commands.command(name="mute", description="Timeout a member (staff)")
    async def mute(self, interaction: discord.Interaction, member: discord.Member, minutes: int = 10, reason: str = "Muted"):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await interaction.response.send_message(embed=_action("🔇", "Muted", 0x5865F2, f"{member.mention} (ID {member.id})", interaction.user.mention, [("⏱️ Duration", f"{minutes} minutes"), ("📄 Reason", reason)]))
        await log_action(interaction.guild, "Muted", member, interaction.user, reason, extra=f"Duration: {minutes} minutes")

    @app_commands.command(name="unmute", description="Remove a member's timeout (staff)")
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await member.timeout(None, reason="Unmuted")
        await interaction.response.send_message(embed=_action("🔊", "Unmuted", 0x57F287, f"{member.mention} (ID {member.id})", interaction.user.mention))
        await log_action(interaction.guild, "Unmuted", member, interaction.user, "Unmuted")

    @app_commands.command(name="timeout", description="Timeout a member for a number of minutes (staff)")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Timeout"):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await member.timeout(timedelta(minutes=minutes), reason=reason)
        await interaction.response.send_message(embed=_action("⏱️", "Timed Out", 0x5865F2, f"{member.mention} (ID {member.id})", interaction.user.mention, [("⏱️ Duration", f"{minutes} minutes"), ("📄 Reason", reason)]))
        await log_action(interaction.guild, "Timed out", member, interaction.user, reason, extra=f"Duration: {minutes} minutes")

    @app_commands.command(name="kick", description="Kick a member (staff)")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Kicked"):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await member.kick(reason=reason)
        await interaction.response.send_message(embed=_action("👢", "Kicked", 0xE67E22, f"{member.mention} (ID {member.id})", interaction.user.mention, [("📄 Reason", reason)]))
        await log_action(interaction.guild, "Kicked", member, interaction.user, reason)

    @app_commands.command(name="ban", description="Ban a member or user (staff)")
    async def ban(self, interaction: discord.Interaction, user: discord.User, reason: str = "Banned"):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.guild.ban(user, reason=reason, delete_message_days=0)
        await interaction.response.send_message(embed=_action("🔨", "Banned", 0xED4245, f"{user.mention} (ID {user.id})", interaction.user.mention, [("📄 Reason", reason)]))
        await log_action(interaction.guild, "Banned", user, interaction.user, reason)

    @app_commands.command(name="unban", description="Unban a user by ID (staff)")
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "Unbanned"):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        try:
            uid = int(user_id.strip())
        except ValueError:
            await interaction.response.send_message("user_id must be a numeric Discord user ID.", ephemeral=True); return
        try:
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=reason)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            await interaction.response.send_message(f"Could not unban {uid}: {e}", ephemeral=True); return
        await interaction.response.send_message(embed=_action("🔓", "Unbanned", 0x57F287, f"{user.mention} (ID {user.id})", interaction.user.mention, [("📄 Reason", reason)]))
        await log_action(interaction.guild, "Unbanned", user, interaction.user, reason)

    @app_commands.command(name="ban_list", description="List banned users (staff)")
    async def ban_list(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        bans = [entry async for entry in interaction.guild.bans(limit=50)]
        text = "\n".join(f"{b.user} ({b.user.id}): {b.reason or '-'}" for b in bans) or "No bans."
        await interaction.response.send_message(embed=emb("Banned Users", text), ephemeral=True)

    @app_commands.command(name="purge", description="Delete recent messages in this channel (staff)")
    async def purge(self, interaction: discord.Interaction, amount: int):
        if not staff_only(interaction) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=max(1, min(200, amount)))
        await interaction.followup.send(embed=_action("🧹", "Messages Purged", 0xE67E22, interaction.channel.mention, interaction.user.mention, [("🗑️ Deleted", f"{len(deleted)} message(s)")]), ephemeral=True)

    @app_commands.command(name="purge_user", description="Delete recent messages from one member (staff)")
    async def purge_user(self, interaction: discord.Interaction, member: discord.Member, amount: int = 20):
        if not staff_only(interaction) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        # Honour the requested amount: scan up to 5x that many recent
        # messages (Discord purge limit is per-scan, not per-author), and
        # stop once `amount` messages from this author are deleted.
        target = max(1, min(200, amount))
        deleted = []
        try:
            async for msg in interaction.channel.history(limit=target * 5):
                if len(deleted) >= target:
                    break
                if msg.author.id == member.id:
                    try:
                        await msg.delete()
                        deleted.append(msg)
                    except discord.HTTPException:
                        pass
        except discord.HTTPException as e:
            await interaction.followup.send(f"Purge failed: {e}", ephemeral=True); return
        await interaction.followup.send(embed=_action("🧹", "Messages Purged", 0xE67E22, f"{member.mention} (ID {member.id})", interaction.user.mention, [("🗑️ Deleted", f"{len(deleted)} message(s)")]), ephemeral=True)

    @app_commands.command(name="set_nick", description="Set a member's nickname (staff)")
    async def set_nick(self, interaction: discord.Interaction, member: discord.Member, nickname: str):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await member.edit(nick=nickname)
        await interaction.response.send_message(embed=_action("✏️", "Nickname Set", 0x5865F2, f"{member.mention} (ID {member.id})", interaction.user.mention, [("🏷️ New nickname", nickname)]))

    @app_commands.command(name="reset_nick", description="Reset a member's nickname (staff)")
    async def reset_nick(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await member.edit(nick=None)
        await interaction.response.send_message(embed=_action("✏️", "Nickname Reset", 0x5865F2, f"{member.mention} (ID {member.id})", interaction.user.mention))

    @app_commands.command(name="add_role", description="Add a role to a member (staff)")
    async def add_role(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await member.add_roles(role, reason=f"Added by {interaction.user}")
        await interaction.response.send_message(embed=_action("➕", "Role Added", 0x57F287, f"{member.mention} (ID {member.id})", interaction.user.mention, [("🎖️ Role", role.mention)]))

    @app_commands.command(name="remove_role", description="Remove a role from a member (staff)")
    async def remove_role(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await member.remove_roles(role, reason=f"Removed by {interaction.user}")
        await interaction.response.send_message(embed=_action("➖", "Role Removed", 0xE67E22, f"{member.mention} (ID {member.id})", interaction.user.mention, [("🎖️ Role", role.mention)]))

    @app_commands.command(name="history", description="Show warnings and notes for a member (staff)")
    async def history(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            warns = conn.execute("SELECT * FROM warns WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10",
                                 (interaction.guild.id, member.id)).fetchall()
            notes = conn.execute("SELECT * FROM notes WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10",
                                 (interaction.guild.id, member.id)).fetchall()
        text = "Warnings:\n" + ("\n".join(f"#{r['id']}: {r['reason']}" for r in warns) or "none")
        text += "\nNotes:\n" + ("\n".join(f"#{r['id']}: {r['note']}" for r in notes) or "none")
        await interaction.response.send_message(embed=emb(f"History for {member}", text), ephemeral=True)

    @app_commands.command(name="timed_out_list", description="List currently timed-out members (staff)")
    async def timed_out_list(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        now = datetime.now(timezone.utc)
        timed = [m for m in interaction.guild.members if m.timed_out_until and m.timed_out_until > now]
        text = "\n".join(f"{m.mention} until {m.timed_out_until:%Y-%m-%d %H:%M} UTC" for m in timed) or "Nobody is timed out."
        await interaction.response.send_message(embed=emb("Timed Out", text), ephemeral=True)

    @app_commands.command(name="voice_kick", description="Disconnect a member from voice (staff)")
    async def voice_kick(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await member.move_to(None, reason="Voice kick")
        await interaction.response.send_message(embed=_action("🔇", "Voice Disconnected", 0xE67E22, f"{member.mention} (ID {member.id})", interaction.user.mention))

    @app_commands.command(name="voice_mute", description="Server-mute a member in voice (staff)")
    async def voice_mute(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await member.edit(mute=True)
        await interaction.response.send_message(embed=_action("🔇", "Voice Muted", 0x5865F2, f"{member.mention} (ID {member.id})", interaction.user.mention))

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
