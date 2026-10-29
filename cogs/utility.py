"""Utility cog: server/user/role info, role audit, ping roles, rolecheck."""
from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import smart
from roles import (CATEGORIES, categorize_role, highest_category,
                   map_guild_roles, ping_roles)


def emb(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=0x57F287,
                         timestamp=datetime.now(timezone.utc))


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction):
        ms = round(self.bot.latency * 1000) if self.bot.latency else 0
        await interaction.response.send_message(f"Pong! Latency: {ms} ms", ephemeral=True)

    @app_commands.command(name="uptime", description="Show how long the bot has been online")
    async def uptime(self, interaction: discord.Interaction):
        delta = datetime.now(timezone.utc) - self.bot.started_at  # type: ignore[attr-defined]
        await interaction.response.send_message(f"Uptime: {delta.days}d {delta.seconds // 3600}h {(delta.seconds // 60) % 60}m", ephemeral=True)

    @app_commands.command(name="serverinfo", description="Show information about this server")
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        await interaction.response.send_message(embed=emb(g.name, f"ID: {g.id}\nOwner: {g.owner}\nMembers: {g.member_count}\n"
                f"Roles: {len(g.roles)}\nChannels: {len(g.channels)}\nCreated: {g.created_at:%Y-%m-%d}"), ephemeral=True)

    @app_commands.command(name="userinfo", description="Show information about a member")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member):
        roles = ", ".join(r.mention for r in member.roles[1:]) or "none"
        await interaction.response.send_message(embed=emb(f"User: {member}", f"ID: {member.id}\nJoined: {member.joined_at:%Y-%m-%d %H:%M} UTC\n"
                f"Account created: {member.created_at:%Y-%m-%d}\nHighest category: {highest_category(member)}\nRoles: {roles}"), ephemeral=True)

    @app_commands.command(name="roleinfo", description="Show information about a role")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        await interaction.response.send_message(embed=emb(f"Role: {role.name}", f"ID: {role.id}\nPosition: {role.position}\n"
                f"Members: {len(role.members)}\nCategory: {categorize_role(role, interaction.guild)}\n"
                f"Colour: {role.colour}\nMentionable: {role.mentionable}"), ephemeral=True)

    @app_commands.command(name="avatar", description="Show a member's avatar")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message(member.display_avatar.url, ephemeral=True)

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

    @app_commands.command(name="pingroles", description="List all notification / ping roles on this server")
    async def pingroles(self, interaction: discord.Interaction):
        roles = ping_roles(interaction.guild)
        text = "\n".join(f"{r.name} — {len(r.members)} members" for r in roles) or "No ping roles found."
        await interaction.response.send_message(embed=emb(f"Ping Roles ({len(roles)})", text), ephemeral=True)

    @app_commands.command(name="channelinfo", description="Show information about a channel")
    async def channelinfo(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.send_message(embed=emb(f"Channel: {channel.name}", f"ID: {channel.id}\nTopic: {channel.topic or '-'}\n"
                f"Slowmode: {channel.slowmode_delay}s\nCategory: {channel.category}"), ephemeral=True)

    @app_commands.command(name="botinfo", description="Show information about this bot")
    async def botinfo(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=emb("NEWR Support", f"User: {self.bot.user}\nGuilds: {len(self.bot.guilds)}\n"
                f"Slash commands: see /help"), ephemeral=True)

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

    @app_commands.command(name="top_roles", description="Show the top roles by position")
    async def top_roles(self, interaction: discord.Interaction):
        roles = sorted([r for r in interaction.guild.roles if r.name != "@everyone"], key=lambda r: r.position, reverse=True)[:15]
        text = "\n".join(f"#{r.position} {r.name} — {len(r.members)} members" for r in roles)
        await interaction.response.send_message(embed=emb("Top Roles", text), ephemeral=True)

    @app_commands.command(name="help", description="List all slash commands by category")
    async def help_cmd(self, interaction: discord.Interaction):
        mapping = map_guild_roles(interaction.guild)
        summary = ", ".join(f"{k}: {len(v)}" for k, v in mapping.items() if v)
        tip = smart.daily_tip()
        await interaction.response.send_message(embed=emb("NEWR Support Help", "Use /ticket_create for help, /faq for answers (it fuzzy-matches, so exact wording is not needed), /verify to verify.\n"
                f"Role categories on this server: {summary}\nFull command list: /command_list\n\n"
                f"💡 Smart tip of the day ({tip['category']}): {tip['text']}\n"
                "Tip categories: security, scam, support, safety, newr — the tip rotates daily, free and local, no AI key needed."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
