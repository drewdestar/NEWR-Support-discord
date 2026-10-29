"""Info cog: command list, server stats, staff list, rules, guidelines."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from roles import is_staff, staff_roles


def emb(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=0x5865F2)


class Info(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _all_commands(self) -> list[str]:
        names: list[str] = []

        def walk(cmds):
            for c in cmds:
                if isinstance(c, app_commands.Group):
                    walk(c.commands)
                else:
                    names.append(c.name)
        walk(self.bot.tree.get_commands())
        return sorted(names)

    @app_commands.command(name="command_list", description="List every slash command on this bot")
    async def command_list(self, interaction: discord.Interaction):
        names = self._all_commands()
        await interaction.response.send_message(embed=emb(f"Commands ({len(names)})", ", ".join(names) or "None loaded."), ephemeral=True)

    @app_commands.command(name="support_info", description="Information about the support system")
    async def support_info(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=emb("Support Info", "Tickets: /ticket_create, /ticket_panel, /ticket_list\n"
                "FAQ: /faq, /faq_list\nFeedback: /feedback\nReports: /report"), ephemeral=True)

    @app_commands.command(name="security_info", description="Information about the security system")
    async def security_info(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=emb("Security Info", "Verification: /verify, /verify_user\n"
                "Protection: /anti_spam, /anti_link, /anti_invite, /anti_raid\nLockdown: /lockdown, /lockdown_server\n"
                "Checks: /account_age, /join_check, /suspicious_check"), ephemeral=True)

    @app_commands.command(name="rules", description="Show the server rules summary")
    async def rules(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=emb("Server Rules", "1. Be respectful to everyone.\n2. No spam, no self-promotion without permission.\n"
                "3. No NSFW or illegal content.\n4. Follow staff directions.\n5. Use tickets for private issues."), ephemeral=True)

    @app_commands.command(name="about", description="About the NEWR Support bot")
    async def about(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=emb("About NEWR Support", "A support + security bot for NEWR LABS.\n"
                "Slash commands only, role-aware, with tickets, verification, anti-raid and moderation tools."), ephemeral=True)

    @app_commands.command(name="staff_list", description="List staff members (support, moderator, admin, owner roles)")
    async def staff_list(self, interaction: discord.Interaction):
        staff = [m for m in interaction.guild.members if is_staff(m)]
        text = "\n".join(f"{m.mention}" for m in staff[:50]) or "No staff found."
        await interaction.response.send_message(embed=emb(f"Staff ({len(staff)})", text), ephemeral=True)

    @app_commands.command(name="guidelines", description="Community guidelines summary")
    async def guidelines(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=emb("Guidelines", "Help each other, keep channels on-topic, do not share private information, "
                "and report problems with /report instead of arguing in public."), ephemeral=True)

    @app_commands.command(name="server_stats", description="Show server statistics")
    async def server_stats(self, interaction: discord.Interaction):
        g = interaction.guild
        online = sum(1 for m in g.members if str(m.status) != "offline")
        bots = sum(1 for m in g.members if m.bot)
        await interaction.response.send_message(embed=emb("Server Stats", f"Members: {g.member_count}\nOnline: {online}\nBots: {bots}\n"
                f"Roles: {len(g.roles)}\nText channels: {len(g.text_channels)}\nVoice channels: {len(g.voice_channels)}"), ephemeral=True)

    @app_commands.command(name="emergency", description="What to do in an emergency on this server")
    async def emergency(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=emb("Emergency", "1. Do not engage further.\n2. Use /report with details.\n"
                "3. Use /staff_ping only if it is urgent and ongoing.\n4. Staff can use /lockdown if a channel is being raided."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Info(bot))
