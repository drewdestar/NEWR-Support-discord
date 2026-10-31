"""Sticky messages (Appy / Welcomer / Supreme Bot feature).

An important message stays at the bottom of a channel: whenever
anyone else posts in that channel, the bot deletes its old sticky
message and reposts it, so it is always last. Staff set it with
/sticky set, remove it with /sticky remove, list with /sticky list.

One top-level slot was traded for this group (/serverinfo, whose
information is already visible in Discord's server settings).
"""
from __future__ import annotations

import discord
from cogs.ui import denied as _denied
from discord import app_commands
from discord.ext import commands

import db
from roles import is_staff

EMBED_COLOR = 0x5865F2


def _ensure() -> None:
    with db._conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sticky_messages("
            "channel_id INTEGER PRIMARY KEY, guild_id INTEGER, "
            "text TEXT, message_id INTEGER)")


def _staff(i: discord.Interaction) -> bool:
    return is_staff(i.user)  # type: ignore[arg-type]


class StickyGroup(commands.GroupCog, group_name="sticky",
                  group_description="Sticky messages (Appy-style)"):
    @app_commands.command(name="set", description="Set a sticky message for a channel (staff)")
    @app_commands.describe(message="The sticky text (kept at the bottom of the channel)",
                           channel="Channel (default: this channel)")
    async def set_sticky(self, interaction: discord.Interaction, message: str,
                         channel: discord.TextChannel | None = None):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        _ensure()
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message("Pick a text channel.", ephemeral=True); return
        with db._conn() as conn:
            old = conn.execute("SELECT message_id FROM sticky_messages WHERE channel_id=?",
                               (target.id,)).fetchone()
        if old and old["message_id"]:
            try:
                old_msg = await target.fetch_message(old["message_id"])
                await old_msg.delete()
            except Exception:
                pass
        msg = await target.send(embed=discord.Embed(
            title="📌 Pinned Info", description=message, colour=EMBED_COLOR))
        with db._conn() as conn:
            conn.execute(
                "INSERT INTO sticky_messages VALUES (?, ?, ?, ?) "
                "ON CONFLICT(channel_id) DO UPDATE SET text=excluded.text, message_id=excluded.message_id",
                (target.id, interaction.guild_id, message, msg.id))
        await interaction.response.send_message(f"Sticky set in {target.mention}.", ephemeral=True)

    @app_commands.command(name="remove", description="Remove the sticky message from a channel (staff)")
    @app_commands.describe(channel="Channel (default: this channel)")
    async def remove_sticky(self, interaction: discord.Interaction,
                            channel: discord.TextChannel | None = None):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        _ensure()
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message("Pick a text channel.", ephemeral=True); return
        with db._conn() as conn:
            old = conn.execute("SELECT message_id FROM sticky_messages WHERE channel_id=?",
                               (target.id,)).fetchone()
            conn.execute("DELETE FROM sticky_messages WHERE channel_id=?", (target.id,))
        if old and old["message_id"]:
            try:
                old_msg = await target.fetch_message(old["message_id"])
                await old_msg.delete()
            except Exception:
                pass
        await interaction.response.send_message(f"Sticky removed from {target.mention}.", ephemeral=True)

    @app_commands.command(name="list", description="List sticky messages (staff)")
    async def list_sticky(self, interaction: discord.Interaction):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        _ensure()
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT channel_id, text FROM sticky_messages WHERE guild_id=?",
                (interaction.guild_id,)).fetchall()
        text = "\n".join(f"<#{r['channel_id']}>: {r['text'][:80]}" for r in rows) or "No stickies."
        await interaction.response.send_message(text, ephemeral=True)


class StickyListener(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Never react to bots (including our own sticky repost), DMs,
        # or the sticky message itself.
        if message.author.bot or message.guild is None:
            return
        _ensure()
        with db._conn() as conn:
            row = conn.execute("SELECT text, message_id FROM sticky_messages WHERE channel_id=?",
                               (message.channel.id,)).fetchone()
        if row is None:
            return
        if row["message_id"] == message.id:
            return
        channel = message.channel
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            if row["message_id"]:
                old_msg = await channel.fetch_message(row["message_id"])
                await old_msg.delete()
        except Exception:
            pass
        try:
            msg = await channel.send(embed=discord.Embed(
                title="📌 Pinned Info", description=row["text"], colour=EMBED_COLOR))
            with db._conn() as conn:
                conn.execute("UPDATE sticky_messages SET message_id=? WHERE channel_id=?",
                             (msg.id, channel.id))
        except Exception:
            pass


async def setup(bot: commands.Bot) -> None:
    _ensure()
    await bot.add_cog(StickyListener(bot))
    await bot.add_cog(StickyGroup(bot))
