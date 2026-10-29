"""DM gate for NEWR Support.

Discord limitation, stated honestly: guild-synced slash commands only
appear inside the server, so DM support cannot be a slash command run
in a DM. DM support therefore works via direct messages (on_message),
while /dm-access (a guild slash command) lets a user check their
DM-access status from inside the server.

Gate (runtime role-name lookup, never hardcoded role IDs):
- Staff / top roles ONLY may chat privately with the bot for support:
  FOUNDER, 👑 Founder, NEWR, 🏛️ Executive, ⭐ Admin, 🛡️ Senior Mod,
  ⚔️ Moderator, 🎯 Team Lead, 🤝 Helper, Security (see roles.py:
  DM_STAFF_ROLE_NAMES, plus the guild owner).
- Regular members (Verified Member, VIP, Elite, Creator, etc.) and
  non-members must NOT get DM support. They get one polite denial
  per burst (10-minute cooldown, to avoid reply-spam) directing them
  to /ticket_create in the NEWR LABS server, and their message is
  NOT stored as a support request.

Staff DM flow:
- "menu" / "help" in DM -> staff DM menu.
- Any other DM text -> stored as a DM support request in SQLite
  (dm_requests table), a summary is forwarded to LOG_CHANNEL_ID
  when set, and the staff member gets a confirmation with the
  request ID. Follow-up in the server is via /ticket_create or by
  sending another DM, which creates another request.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import db
import smart
from roles import DM_STAFF_ROLE_NAMES, dm_staff_roles, is_dm_staff

def _env_int(name: str):
    try:
        return int(os.environ[name]) if os.environ.get(name) else None
    except ValueError:
        return None


NEWR_LABS_GUILD_ID = _env_int("GUILD_ID")
LOG_CHANNEL_ID = _env_int("LOG_CHANNEL_ID")
_DENIAL_COOLDOWN_SECONDS = 600  # one denial per user per burst

STAFF_MENU = (
    "👋 Halo, staff NEWR LABS! Kamu punya akses DM support.\n\n"
    "**DM Staff Menu — NEWR Support**\n"
    "• Kirim pesan apa pun di DM ini untuk membuat support request baru.\n"
    "  Request-nya tersimpan dan diteruskan ke log channel staff kalau sudah disetel.\n"
    "• Ketik `menu` untuk melihat menu ini lagi.\n"
    "• Untuk tiket penuh di server, pakai `/ticket_create` di NEWR LABS.\n"
    "• Cek akses DM kamu kapan saja dari server dengan `/dm-access`."
)

MEMBER_DENIAL = (
    "Halo! Maaf ya, DM support NEWR Support hanya untuk staff dan role "
    "tertinggi NEWR LABS saja, jadi DM ini tidak bisa diproses sebagai "
    "support request.\n\n"
    "Kalau kamu member, silakan pakai `/ticket_create` di server NEWR LABS, "
    "staff akan bantu kamu di sana. Terima kasih sudah menghubungi kami!"
)

NON_MEMBER_DENIAL = (
    "Halo! Maaf ya, DM support NEWR Support hanya untuk staff dan role "
    "tertinggi NEWR LABS saja. Kamu belum terdaftar sebagai member NEWR LABS, "
    "jadi DM ini tidak bisa diproses.\n\n"
    "Silakan join server NEWR LABS dulu, lalu pakai `/ticket_create` di "
    "server kalau kamu butuh bantuan. Terima kasih!"
)


def _resolve_guild(bot: commands.Bot, fallback: discord.Guild | None = None) -> discord.Guild | None:
    if NEWR_LABS_GUILD_ID:
        guild = bot.get_guild(NEWR_LABS_GUILD_ID)
        if guild is not None:
            return guild
        # Fail closed: never fall back to an arbitrary other server for
        # a DM staff check when the target guild is not visible.
        return fallback if fallback is not None and fallback.id == NEWR_LABS_GUILD_ID else None
    if fallback is not None:
        return fallback
    return None


async def _resolve_member(bot: commands.Bot, user_id: int,
                          fallback_guild: discord.Guild | None = None) -> tuple[discord.Guild | None, discord.Member | None]:
    guild = _resolve_guild(bot, fallback_guild)
    if guild is None:
        return None, None
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            member = None
    return guild, member


class DMGate(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._denied_at: dict[int, float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # DM only: guild messages are handled by the other cogs.
        if message.author.bot or message.guild is not None:
            return
        user = message.author
        guild, member = await _resolve_member(self.bot, user.id)
        if guild is None:
            await message.channel.send(
                "Maaf, bot belum terhubung ke server NEWR LABS, jadi akses DM "
                "belum bisa diverifikasi. Silakan pakai /ticket_create di server NEWR LABS.")
            return
        if member is None or not is_dm_staff(member):
            # One denial per burst: reply once, then ignore repeats for
            # 10 minutes so a member cannot spam the bot into replying.
            now = time.time()
            if now - self._denied_at.get(user.id, 0) < _DENIAL_COOLDOWN_SECONDS:
                return
            self._denied_at[user.id] = now
            await message.channel.send(NON_MEMBER_DENIAL if member is None else MEMBER_DENIAL)
            return

        # Staff / top roles only, from here on.
        text = (message.content or "").strip()
        if not text or text.lower() in ("menu", "help", "halo", "hi", "hello"):
            tip = smart.daily_tip()
            await message.channel.send(STAFF_MENU + f"\n\n💡 Tip of the day ({tip['category']}): {tip['text']}")
            return
        # Staff-only smart tip in DM (on_message): "tip"/"tips" returns the
        # rotating local tip instead of being stored as a support request.
        if text.lower() in ("tip", "tips", "tips please", "smart tip"):
            tip = smart.daily_tip()
            await message.channel.send(f"💡 Tip of the day ({tip['category']}): {tip['text']}")
            return
        # Staff DM support request: store it, forward a summary to the
        # log channel when configured, confirm with the request ID.
        request_id = db.add_row(
            "dm_requests", guild_id=guild.id, user_id=user.id,
            text=text[:2000], status="open", created_at=db.now())
        if LOG_CHANNEL_ID:
            channel = guild.get_channel(LOG_CHANNEL_ID)
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.send(
                        f"📩 **DM support request #{request_id}** dari {user.mention} "
                        f"({user}, staff roles: {', '.join(r.name for r in dm_staff_roles(member))})\n"
                        f"> {text[:1000]}")
                except discord.HTTPException:
                    pass
        await message.channel.send(
            f"✅ Support request DM kamu tersimpan sebagai **#{request_id}**.\n"
            f"{smart.triage_text(text)}\n"
            f"Staff bisa menindaklanjuti dari log channel, atau kamu bisa buat tiket penuh "
            f"di server dengan `/ticket_create`. Kirim pesan lagi di DM ini untuk request baru, "
            f"atau ketik `menu` untuk menu staff.")

    @app_commands.command(name="dm-access", description="Check whether you have staff DM access to NEWR Support")
    async def dm_access(self, interaction: discord.Interaction):
        # Slash commands do not run in DMs (guild-synced), so this is
        # expected to run inside a server; handle a DM invocation anyway.
        if interaction.guild is None:
            await interaction.response.send_message(
                "Perintah ini hanya bisa dicek dari dalam server. DM support sendiri "
                "berjalan lewat pesan DM (bukan slash command di DM) — lihat README.",
                ephemeral=True)
            return
        _, member = await _resolve_member(
            self.bot, interaction.user.id, fallback_guild=interaction.guild)
        if member is None:
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="DM Access: Non-member",
                    description=("Kamu belum terdaftar sebagai member NEWR LABS, jadi kamu "
                                 "tidak punya akses DM support. Join server NEWR LABS dulu, "
                                 "lalu pakai /ticket_create di server kalau butuh bantuan."),
                    color=0xED4245, timestamp=datetime.now(timezone.utc)),
                ephemeral=True)
            return
        staff_roles = dm_staff_roles(member)
        if is_dm_staff(member):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="DM Access: Staff ✅",
                    description=("Kamu punya akses DM support NEWR Support.\n"
                                 f"Role staff/top kamu: {', '.join(r.name for r in staff_roles) or 'guild owner'}\n"
                                 "Kirim DM ke bot ini untuk membuat support request, atau ketik `menu` di DM."),
                    color=0x57F287, timestamp=datetime.now(timezone.utc)),
                ephemeral=True)
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="DM Access: Member only",
                description=("DM support NEWR Support hanya untuk staff dan role tertinggi "
                             "(FOUNDER, 👑 Founder, NEWR, 🏛️ Executive, ⭐ Admin, 🛡️ Senior Mod, "
                             "⚔️ Moderator, 🎯 Team Lead, 🤝 Helper, Security).\n"
                             "Sebagai member, silakan pakai /ticket_create di server NEWR LABS."),
                color=0xFEE75C, timestamp=datetime.now(timezone.utc)),
            ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DMGate(bot))
