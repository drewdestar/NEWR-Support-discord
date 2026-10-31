"""Utility cog: server/user/role info, role audit, ping roles, rolecheck."""
from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import smart
from cogs.ui import denied as _denied, err as _err, make as _make, ok as _ok
from roles import (CATEGORIES, categorize_role, highest_category,
                   is_staff, map_guild_roles, ping_roles)


def emb(title: str, desc: str) -> discord.Embed:
    from cogs.ui import panel
    return panel(title, desc, 0x57F287)


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="say", description="Send a message as the bot to a channel, with mentions (staff)")
    @app_commands.describe(
        message="Message text. Mentions typed here (@everyone, @role, #channel) are sent as-is and will ping/link if valid.",
        channel="Target text channel (default: the channel you run this in)",
        category="Target category: send the message to every text channel in it",
        ping_user="Also mention this user at the start of the message",
        ping_role="Also mention this role at the start of the message",
        ping_everyone="Also mention @everyone at the start of the message")
    async def say(self, interaction: discord.Interaction, message: str,
                  channel: discord.TextChannel | None = None,
                  category: discord.CategoryChannel | None = None,
                  ping_user: discord.User | None = None,
                  ping_role: discord.Role | None = None,
                  ping_everyone: bool = False):
        if not is_staff(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        parts: list[str] = []
        if ping_everyone:
            parts.append("@everyone")
        if ping_role is not None:
            parts.append(ping_role.mention)
        if ping_user is not None:
            parts.append(ping_user.mention)
        if message:
            parts.append(message)
        content = " ".join(parts).strip()
        if not content:
            await interaction.response.send_message("Nothing to send.", ephemeral=True); return
        if category is not None:
            targets = sorted(category.text_channels, key=lambda c: c.position)
        elif channel is not None:
            targets = [channel]
        elif isinstance(interaction.channel, discord.TextChannel):
            targets = [interaction.channel]
        else:
            await interaction.response.send_message(
                "Pick a channel or category to send to.", ephemeral=True); return
        if not targets:
            await interaction.response.send_message(
                "That category has no text channels.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        # Discord's per-message limit is 2000 characters; split long
        # messages so a long announcement does not fail outright.
        chunks = [content[i:i + 2000] for i in range(0, len(content), 2000)]
        sent, failed = [], []
        for target in targets:
            try:
                for chunk in chunks:
                    await target.send(chunk)
                sent.append(target.mention)
            except Exception as e:
                failed.append(f"{target.mention} ({e})")
        note = ""
        if category is not None:
            note = "\nNote: Discord has no category mention, so a category target means the message was sent to every text channel in that category."
        await interaction.followup.send(
            f"✅ Sent to: {', '.join(sent) or 'none'}"
            + (f"\n❌ Failed: {', '.join(failed)}" if failed else "")
            + note, ephemeral=True)

    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction):
        ms = round(self.bot.latency * 1000) if self.bot.latency else 0
        status = "🟢 Excellent" if ms < 100 else "🟡 Good" if ms < 250 else "🔴 Slow"
        await interaction.response.send_message(embed=_make("🏓 Pong!", fields=[("⏱️ Latency", f"{ms} ms", True), ("📶 Status", status, True)]), ephemeral=True)

    @app_commands.command(name="userinfo", description="Show information about a member")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member):
        roles = ", ".join(r.mention for r in member.roles[1:]) or "none"
        await interaction.response.send_message(embed=_make(f"👤 {member}", fields=[("🆔 ID", str(member.id), True), ("📅 Joined server", f"{member.joined_at:%Y-%m-%d %H:%M} UTC" if member.joined_at else "—", True), ("🎂 Account created", f"{member.created_at:%Y-%m-%d}", True), ("🏷️ Highest category", highest_category(member), True), ("🎖️ Roles", roles, False)], thumbnail=member.display_avatar.url), ephemeral=True)

    @app_commands.command(name="roleinfo", description="Show information about a role")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.send_message(embed=_make(f"🎖️ {role.name}", fields=[("🆔 ID", str(role.id), True), ("📍 Position", str(role.position), True), ("👥 Members", str(len(role.members)), True), ("🏷️ Category", categorize_role(role, interaction.guild), True), ("🎨 Colour", str(role.colour), True), ("📣 Mentionable", "Yes" if role.mentionable else "No", True)]), ephemeral=True)

    @app_commands.command(name="avatar", description="Show a member's avatar")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member):
        embed = _make(f"🖼️ Avatar — {member}", thumbnail=member.display_avatar.url)
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="roles", description="Audit every role: position, member count, and mapped category")
    async def roles(self, interaction: discord.Interaction):
        """Audit: lists ALL guild.roles, so in NEWR LABS it lists all 38
        roles by name (the duplicate Jockie Music entry in the source list
        appears once in Discord's live role list)."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        lines = []
        for role in sorted(guild.roles, key=lambda r: r.position, reverse=True):
            if role.name == "@everyone":
                continue
            lines.append(f"#{role.position} {role.name} — {len(role.members)} members — {categorize_role(role, guild)}")
        # Discord embeds cap at 4096 chars; split into chunks if needed.
        text = "\n".join(lines) or "No roles."
        for chunk_start in range(0, len(text), 4000):
            chunk = text[chunk_start:chunk_start + 4000]
            if chunk_start == 0:
                await interaction.followup.send(embed=emb(f"Role Audit ({len(lines)} roles)", chunk), ephemeral=True)
            else:
                await interaction.followup.send(embed=emb("Role Audit (continued)", chunk), ephemeral=True)

    @app_commands.command(name="rolecheck", description="Check one member's roles against the role mapping")
    async def rolecheck(self, interaction: discord.Interaction, member: discord.Member):
        lines = [f"{r.name} — {categorize_role(r, interaction.guild)}" for r in sorted(member.roles, key=lambda r: r.position, reverse=True) if r.name != "@everyone"]
        text = "\n".join(lines) or "No roles."
        await interaction.response.send_message(embed=emb(f"Role Check: {member} (highest: {highest_category(member)})", text), ephemeral=True)

    @app_commands.command(name="member_permissions", description="Show a member's key permissions")
    async def member_permissions(self, interaction: discord.Interaction, member: discord.Member):
        p = member.guild_permissions
        keys = [k for k in ("administrator", "manage_guild", "kick_members", "ban_members", "manage_messages",
                            "moderate_members", "manage_roles", "manage_channels", "send_messages") if getattr(p, k)]
        await interaction.response.send_message(embed=emb(f"Permissions: {member}", ", ".join(keys) or "No special permissions"), ephemeral=True)

    @app_commands.command(name="role_members", description="List members holding a role")
    async def role_members(self, interaction: discord.Interaction, role: discord.Role):
        names = ", ".join(m.mention for m in role.members[:50]) or "Nobody."
        await interaction.response.send_message(embed=emb(f"Members with {role.name} ({len(role.members)})", names), ephemeral=True)

    @app_commands.command(name="help", description="List all slash commands by category")
    async def help_cmd(self, interaction: discord.Interaction):
        tip = smart.daily_tip()
        embed = _make("📖 NEWR Support — Help",
                      "Everything you need, in one place. Staff commands need a staff or top role.",
                      thumbnail=interaction.guild.icon.url if interaction.guild and interaction.guild.icon else None)
        embed.add_field(name="🎟️ Get Help", value="`/ticket_create` — open a private ticket\n`/faq` — answers, fuzzy-matched\n`/report` — report a member\n`/suggest` · `/bug` · `/feedback`", inline=False)
        embed.add_field(name="🔒 Verify", value="`/verify` — one captcha-gated panel in #✔️-verification\nNo role is given before a correct captcha answer.", inline=False)
        embed.add_field(name="📝 Apply", value="`/apply submit` — staff application (form or DM)\nStaff review it in #apply and DM you the result.", inline=False)
        embed.add_field(name="🛡️ Staff & Moderation", value="`/warn` · `/mute` · `/kick` · `/ban` · `/purge`\n`/ticket_list` · `/report_list` · `/appeal_list`\n`/backup` · `/say` · `/security_status`", inline=False)
        embed.add_field(name="ℹ️ Info & Utility", value="`/userinfo` · `/roleinfo` · `/server_stats` · `/ping`\n`/roles` · `/rolecheck` · `/staff_list`", inline=False)
        embed.add_field(name="⚠️ Channel Rule", value="Member commands only work in their designated channel (#🤖-bot-commands, #⚠️-reports, #💡-suggestions, #🐛-bug-reports, #📝-feedback, #🎟️-ticket). Staff and top roles are exempt.", inline=False)
        embed.add_field(name=f"💡 Smart Tip — {tip['category']}", value=tip['text'], inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)




async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
