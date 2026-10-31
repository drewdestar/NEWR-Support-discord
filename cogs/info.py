"""Info cog: command list, server stats, staff list, rules."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from roles import is_staff, staff_roles
from cogs.ui import make as _make


def emb(title: str, desc: str) -> discord.Embed:
    from cogs.ui import panel
    return panel(title, desc, 0x5865F2)


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

    @app_commands.command(name="rules", description="Show the server rules summary")
    async def rules(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=_make("📜 Server Rules", fields=[("1️⃣ Respect", "Be respectful to everyone.", False), ("2️⃣ No Spam", "No spam, no self-promotion without permission.", False), ("3️⃣ Safe Content", "No NSFW or illegal content.", False), ("4️⃣ Staff Directions", "Follow staff directions.", False), ("5️⃣ Private Issues", "Use tickets for private issues.", False)]), ephemeral=True)

    @app_commands.command(name="staff_list", description="List staff members (support, moderator, admin, owner roles)")
    async def staff_list(self, interaction: discord.Interaction):
        staff = [m for m in interaction.guild.members if is_staff(m)]
        text = "\n".join(f"{m.mention}" for m in staff[:50]) or "No staff found."
        await interaction.response.send_message(embed=emb(f"Staff ({len(staff)})", text), ephemeral=True)

    @app_commands.command(name="server_stats", description="Show server statistics")
    async def server_stats(self, interaction: discord.Interaction):
        g = interaction.guild
        online = sum(1 for m in g.members if str(m.status) != "offline")
        bots = sum(1 for m in g.members if m.bot)
        await interaction.response.send_message(embed=_make("📊 Server Stats", fields=[("👥 Members", str(g.member_count), True), ("🟢 Online", str(online), True), ("🤖 Bots", str(bots), True), ("🎖️ Roles", str(len(g.roles)), True), ("💬 Text channels", str(len(g.text_channels)), True), ("🔊 Voice channels", str(len(g.voice_channels)), True)], thumbnail=g.icon.url if g.icon else None), ephemeral=True)



async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Info(bot))
