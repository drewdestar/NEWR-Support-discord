"""Security cog: verification, anti-spam/link/raid, lockdown, quarantine."""
from __future__ import annotations

import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

import db
from roles import categorize_role, is_staff, map_guild_roles

EMBED_COLOR = 0xED4245


def emb(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=EMBED_COLOR,
                         timestamp=datetime.now(timezone.utc))


def staff_only(i: discord.Interaction) -> bool:
    return is_staff(i.user)  # type: ignore[arg-type]


class VerifyView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Me", style=discord.ButtonStyle.success, emoji="✅", custom_id="newr_support_verify")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        guild = interaction.guild
        verified = [r for r in guild.roles if categorize_role(r, guild) == "verified"]
        if not verified:
            await interaction.response.send_message("No verified role found on this server.", ephemeral=True); return
        await interaction.user.add_roles(*verified, reason="Self-verification")  # type: ignore[arg-type]
        await interaction.response.send_message("You are verified!", ephemeral=True)


class Security(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._msg_times: dict[int, list[float]] = defaultdict(list)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        guild, author = message.guild, message.author
        if is_staff(author):
            return
        # Anti-link / anti-invite / banned words
        content = message.content
        try:
            if db.get_setting(guild.id, "anti_link") == "on" and re.search(r"https?://", content):
                await message.delete(); await message.channel.send(f"{author.mention} links are not allowed here.", delete_after=10); return
            if db.get_setting(guild.id, "anti_invite") == "on" and "discord.gg/" in content:
                await message.delete(); return
            with db._conn() as conn:
                words = [r["word"] for r in conn.execute("SELECT word FROM banned_words WHERE guild_id=?", (guild.id,)) if r["word"].strip()]
            # Word-boundary matching: a banned substring inside an innocent
            # word must not trigger deletion.
            if any(re.search(rf"\b{re.escape(w.lower())}\b", content.lower()) for w in words):
                await message.delete(); return
        except discord.HTTPException:
            return
        # Anti-spam: >5 messages in 10s
        if db.get_setting(guild.id, "anti_spam") == "on":
            now = time.time()
            times = [t for t in self._msg_times[author.id] if now - t < 10]
            times.append(now); self._msg_times[author.id] = times
            if len(times) > 5:
                try:
                    await message.delete()
                    await message.channel.send(f"{author.mention} slow down, you are sending messages too fast.", delete_after=10)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        age_days = (datetime.now(timezone.utc) - member.created_at).days
        min_age = int(db.get_setting(member.guild.id, "min_account_age_days", "0"))
        log_id = db.get_setting(member.guild.id, "log_channel", "")
        if log_id:
            channel = member.guild.get_channel(int(log_id))
            if channel:
                await channel.send(f"👋 {member.mention} joined. Account age: {age_days} days.")  # type: ignore[union-attr]
        if db.get_setting(member.guild.id, "anti_raid") == "on" and min_age and age_days < min_age:
            muted = [r for r in member.guild.roles if categorize_role(r, member.guild) == "muted"]
            if muted:
                await member.add_roles(*muted, reason="Anti-raid: new account")

    def _toggle(self, interaction: discord.Interaction, key: str, action: str) -> str:
        if action == "status":
            return f"{key} is currently: {db.get_setting(interaction.guild.id, key)}"
        db.set_setting(interaction.guild.id, key, "on" if action == "enable" else "off")
        return f"{key} set to {action}d."

    def _toggle_cmd(self, name: str, desc: str, key: str):
        async def handler(self, interaction: discord.Interaction, action: app_commands.Choice[str]):  # type: ignore
            if not staff_only(interaction):
                await interaction.response.send_message("Staff only.", ephemeral=True); return
            await interaction.response.send_message(self._toggle(interaction, key, action.value), ephemeral=True)
        handler.__name__ = name
        return app_commands.command(name=name, description=desc)(
            app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("enable", "disable", "status")])(handler))

    # Verification
    @app_commands.command(name="verify", description="Post a self-verification button")
    async def verify(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=emb("Verification", "Click Verify Me to get the verified role."),
                                                view=VerifyView())

    @app_commands.command(name="captcha_verify", description="Post a captcha-style verification button (staff)")
    async def captcha_verify(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        await interaction.response.send_message(embed=emb("Human Check", "Press Verify Me to prove you are human."),
                                                view=VerifyView())

    @app_commands.command(name="verify_user", description="Manually verify a member (staff)")
    async def verify_user(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        verified = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "verified"]
        unverified = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "unverified"]
        await member.add_roles(*verified, reason="Manual verification")
        if unverified:
            await member.remove_roles(*unverified, reason="Manual verification")
        await interaction.response.send_message(f"{member.mention} has been verified.")

    @app_commands.command(name="account_age", description="Check a member's account age")
    async def account_age(self, interaction: discord.Interaction, member: discord.Member):
        age = datetime.now(timezone.utc) - member.created_at
        await interaction.response.send_message(embed=emb("Account Age", f"{member.mention}\nCreated: {member.created_at:%Y-%m-%d}\nAge: {age.days} days"), ephemeral=True)

    @app_commands.command(name="join_check", description="Risk-check a member joining / already in the server")
    async def join_check(self, interaction: discord.Interaction, member: discord.Member):
        age_days = (datetime.now(timezone.utc) - member.created_at).days
        risk = 0
        reasons = []
        if age_days < 7: risk += 40; reasons.append("Account under 7 days old")
        if age_days < 30: risk += 20; reasons.append("Account under 30 days old")
        if member.avatar is None: risk += 20; reasons.append("No avatar")
        if member.bot: risk += 10; reasons.append("Bot account")
        level = "Low" if risk < 30 else "Medium" if risk < 70 else "High"
        await interaction.response.send_message(embed=emb("Join Check", f"{member.mention}\nRisk: {level} ({risk}/100)\n" + "\n".join(reasons) or "No risk flags"), ephemeral=True)

    @app_commands.command(name="suspicious_check", description="List members with accounts under 7 days old (staff)")
    async def suspicious_check(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        now = datetime.now(timezone.utc)
        young = [m for m in interaction.guild.members if (now - m.created_at).days < 7]
        text = "\n".join(f"{m.mention} — {(now - m.created_at).days}d" for m in young[:30]) or "No accounts under 7 days old."
        await interaction.response.send_message(embed=emb("Suspicious Accounts", text), ephemeral=True)

    # Toggles are registered in __init__-style below via explicit commands:
    @app_commands.command(name="anti_spam", description="Enable, disable or check anti-spam (staff)")
    @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("enable", "disable", "status")])
    async def anti_spam(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        await interaction.response.send_message(self._toggle(interaction, "anti_spam", action.value), ephemeral=True)

    @app_commands.command(name="anti_link", description="Enable, disable or check anti-link (staff)")
    @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("enable", "disable", "status")])
    async def anti_link(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        await interaction.response.send_message(self._toggle(interaction, "anti_link", action.value), ephemeral=True)

    @app_commands.command(name="anti_invite", description="Enable, disable or check anti-invite (staff)")
    @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("enable", "disable", "status")])
    async def anti_invite(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        await interaction.response.send_message(self._toggle(interaction, "anti_invite", action.value), ephemeral=True)

    @app_commands.command(name="anti_raid", description="Enable, disable or check anti-raid mode (staff)")
    @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("enable", "disable", "status")])
    async def anti_raid(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        await interaction.response.send_message(self._toggle(interaction, "anti_raid", action.value), ephemeral=True)

    @app_commands.command(name="raid_status", description="Show raid / security protection status")
    async def raid_status(self, interaction: discord.Interaction):
        g = interaction.guild.id
        text = "\n".join(f"{k}: {db.get_setting(g, k)}" for k in ("anti_spam", "anti_link", "anti_invite", "anti_raid"))
        await interaction.response.send_message(embed=emb("Raid Status", text), ephemeral=True)

    @app_commands.command(name="security_status", description="Show all security settings")
    async def security_status(self, interaction: discord.Interaction):
        g = interaction.guild.id
        text = "\n".join(f"{k}: {db.get_setting(g, k)}" for k in ("anti_spam", "anti_link", "anti_invite", "anti_raid", "min_account_age_days"))
        await interaction.response.send_message(embed=emb("Security Status", text), ephemeral=True)

    @app_commands.command(name="security_config", description="Set minimum account age in days for new joins (staff)")
    async def security_config(self, interaction: discord.Interaction, min_account_age_days: int):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        db.set_setting(interaction.guild.id, "min_account_age_days", str(max(0, min_account_age_days)))
        await interaction.response.send_message(f"Minimum account age set to {min_account_age_days} days.")

    # Lockdown / slowmode
    @app_commands.command(name="lockdown", description="Lock the current channel (staff)")
    async def lockdown(self, interaction: discord.Interaction):
        if not staff_only(interaction) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Staff only, in a text channel.", ephemeral=True); return
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message("🔒 Channel locked.")

    @app_commands.command(name="unlock", description="Unlock the current channel (staff)")
    async def unlock(self, interaction: discord.Interaction):
        if not staff_only(interaction) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Staff only, in a text channel.", ephemeral=True); return
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=None)
        await interaction.response.send_message("🔓 Channel unlocked.")

    @app_commands.command(name="lockdown_server", description="Lock all text channels (staff)")
    async def lockdown_server(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        failed = 0
        for ch in interaction.guild.text_channels:
            try:
                await ch.set_permissions(interaction.guild.default_role, send_messages=False)
            except discord.HTTPException:
                failed += 1
        await interaction.followup.send(f"🔒 Server locked." + (f" ({failed} channel(s) failed — check bot permissions.)" if failed else ""), ephemeral=True)

    @app_commands.command(name="unlock_server", description="Unlock all text channels (staff)")
    async def unlock_server(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        failed = 0
        for ch in interaction.guild.text_channels:
            try:
                await ch.set_permissions(interaction.guild.default_role, send_messages=None)
            except discord.HTTPException:
                failed += 1
        await interaction.followup.send(f"🔓 Server unlocked." + (f" ({failed} channel(s) failed — check bot permissions.)" if failed else ""), ephemeral=True)

    @app_commands.command(name="slowmode", description="Set slowmode in seconds for the current channel (staff)")
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        if not staff_only(interaction) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Staff only, in a text channel.", ephemeral=True); return
        clamped = max(0, min(21600, seconds))
        await interaction.channel.edit(slowmode_delay=clamped)
        await interaction.response.send_message(f"Slowmode set to {clamped} seconds.")

    # Quarantine / trusted / watchlist / banned words
    @app_commands.command(name="quarantine", description="Quarantine a member with the muted role (staff)")
    async def quarantine(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Quarantine"):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        muted = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "muted"]
        if not muted:
            await interaction.response.send_message("No muted role found.", ephemeral=True); return
        await member.add_roles(*muted, reason=reason)
        await interaction.response.send_message(f"{member.mention} quarantined. Reason: {reason}")

    @app_commands.command(name="unquarantine", description="Remove quarantine from a member (staff)")
    async def unquarantine(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        muted = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "muted"]
        await member.remove_roles(*muted, reason="Unquarantine")
        await interaction.response.send_message(f"{member.mention} unquarantined.")

    @app_commands.command(name="trusted_add", description="Give a member a trusted/helper role (staff)")
    async def trusted_add(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        roles = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "trusted"]
        if not roles:
            await interaction.response.send_message("No trusted role found.", ephemeral=True); return
        await member.add_roles(*roles, reason="Trusted")
        await interaction.response.send_message(f"{member.mention} given trusted roles.")

    @app_commands.command(name="trusted_remove", description="Remove trusted roles from a member (staff)")
    async def trusted_remove(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        roles = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "trusted"]
        await member.remove_roles(*roles, reason="Trusted removed")
        await interaction.response.send_message(f"Trusted roles removed from {member.mention}.")

    @app_commands.command(name="watchlist_add", description="Add a member to the security watchlist (staff)")
    async def watchlist_add(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        with db._conn() as conn:
            conn.execute("INSERT INTO watchlist VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET reason=excluded.reason",
                         (interaction.guild.id, member.id, reason))
        await interaction.response.send_message(f"{member.mention} added to the watchlist.")

    @app_commands.command(name="watchlist_list", description="List the security watchlist (staff)")
    async def watchlist_list(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        rows = db.list_rows("watchlist", interaction.guild.id, 50)
        text = "\n".join(f"<@{r['user_id']}>: {r['reason']}" for r in rows) or "Watchlist empty."
        await interaction.response.send_message(embed=emb("Watchlist", text), ephemeral=True)

    @app_commands.command(name="watchlist_remove", description="Remove a member from the watchlist (staff)")
    async def watchlist_remove(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        with db._conn() as conn:
            conn.execute("DELETE FROM watchlist WHERE guild_id=? AND user_id=?", (interaction.guild.id, member.id))
        await interaction.response.send_message(f"{member.mention} removed from the watchlist.")

    @app_commands.command(name="ban_word_add", description="Add a banned word (staff)")
    async def ban_word_add(self, interaction: discord.Interaction, word: str):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        if not word.strip():
            await interaction.response.send_message("Banned word cannot be empty (an empty word would match everything).", ephemeral=True); return
        with db._conn() as conn:
            conn.execute("INSERT OR IGNORE INTO banned_words VALUES (?, ?)", (interaction.guild.id, word.lower()))
        await interaction.response.send_message(f"Banned word added: {word}")

    @app_commands.command(name="ban_word_list", description="List banned words (staff)")
    async def ban_word_list(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        with db._conn() as conn:
            rows = conn.execute("SELECT word FROM banned_words WHERE guild_id=?", (interaction.guild.id,)).fetchall()
        text = ", ".join(r["word"] for r in rows) or "No banned words."
        await interaction.response.send_message(embed=emb("Banned Words", text), ephemeral=True)

    @app_commands.command(name="ban_word_remove", description="Remove a banned word (staff)")
    async def ban_word_remove(self, interaction: discord.Interaction, word: str):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        with db._conn() as conn:
            conn.execute("DELETE FROM banned_words WHERE guild_id=? AND word=?", (interaction.guild.id, word.lower()))
        await interaction.response.send_message(f"Banned word removed: {word}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Security(bot))
