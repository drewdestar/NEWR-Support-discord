"""Report flow: report channel, staff action buttons, warn ladder,
mute durations, ban confirm, false-report consequences, appeals.

Flow:
  /report (in cogs.support, category Ringan/Sedang/Parah + optional
  bukti) -> embed posted to the report channel with ReportView.
  Staff buttons on that embed (staff-only, checked in every callback):
    Warn N  -> next warn level for the target (Warn 1 -> 2 -> 3;
               after Warn 3 the button is disabled, staff must mute/ban)
    Mute    -> second button row: 10 menit / 1 jam / 6 jam / 24 jam / 7 hari
    Ban     -> confirm step first ("Ya, Ban" / "Batal"), then ban
    Laporan Palsu -> report marked false, the REPORTER gets the next
               warn level (false reports have consequences)
    Tutup   -> close without action
  Every warn/mute/ban from this flow DMs the punished user with an
  "Ajukan Appeal" button (DM is sent BEFORE a ban, since a banned user
  cannot use /appeal in the server). The appeal modal posts to the
  appeal channel, where staff accept/reject it:
    accept warn -> warns cleared + Warn roles removed
    accept mute -> timeout removed
    accept ban  -> unbanned
  Channels: report channel = DB setting report_channel, else a channel
  named "reports"/"report", else created as staff-only "reports",
  else the log channel. Appeal channel likewise ("appeals"/"appeal").
  Creating a channel needs Manage Channels; failure falls back silently.

Views with per-report/per-appeal custom_ids are re-registered on
startup for open reports/appeals in setup(), so buttons survive a
bot restart as long as the case is still open.
"""
from __future__ import annotations

from datetime import timedelta

import discord
from cogs.ui import denied as _denied
from discord.ext import commands

import db
from cogs.modlog import log_action
from roles import is_staff, support_roles

MUTE_DURATIONS = [(10, "10 minutes"), (60, "1 hour"), (360, "6 hours"),
                  (1440, "24 hours"), (10080, "7 days")]
WARN_ROLE_NAMES = ["Warn 1", "Warn 2", "Warn 3"]
CATEGORY_EMOJI = {"Low": "🟢", "Medium": "🟡", "Severe": "🔴"}


# ---------- helpers ----------

def count_warns(guild_id: int, user_id: int) -> int:
    with db._conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM warns WHERE guild_id=? AND user_id=?",
                           (guild_id, user_id)).fetchone()
    return row[0] if row else 0


def count_open_reports(guild_id: int, target_id: int) -> int:
    with db._conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM reports WHERE guild_id=? AND target_id=? "
                           "AND (status IS NULL OR status='open')",
                           (guild_id, target_id)).fetchone()
    return row[0] if row else 0


def get_report(rid: int):
    with db._conn() as conn:
        return conn.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()


def mark_report(rid: int, status: str, action: str) -> None:
    with db._conn() as conn:
        conn.execute("UPDATE reports SET status=?, action=? WHERE id=?",
                     (status, action, rid))


async def _member_or_user(guild: discord.Guild, user_id: int):
    member = guild.get_member(user_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(user_id)
    except Exception:
        pass
    try:
        return await guild.fetch_user(user_id)
    except Exception:
        return None


async def resolve_channel(guild: discord.Guild, setting_key: str,
                          names: list[str], create_name: str):
    """Staff-only channel for reports/appeals, created if missing."""
    raw = db.get_setting(guild.id, setting_key, "")
    if raw.isdigit():
        ch = guild.get_channel(int(raw))
        if isinstance(ch, discord.TextChannel):
            return ch
    for name in names:
        ch = discord.utils.get(guild.text_channels, name=name)
        if ch is not None:
            db.set_setting(guild.id, setting_key, str(ch.id))
            return ch
    # Create it staff-only (everyone cannot read, staff + bot can).
    try:
        overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        for role in support_roles(guild):
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                           read_message_history=True)
        if guild.me is not None:
            overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                               read_message_history=True)
        ch = await guild.create_text_channel(create_name, overwrites=overwrites,
                                             reason=f"NEWR Support {create_name} channel")
        db.set_setting(guild.id, setting_key, str(ch.id))
        return ch
    except Exception:
        pass
    # Fallback: the log channel, so a report is never silently lost.
    from cogs.modlog import log_channel
    return await log_channel(guild)


async def resolve_report_channel(guild: discord.Guild):
    return await resolve_channel(guild, "report_channel", ["reports", "report"], "reports")


async def resolve_appeal_channel(guild: discord.Guild):
    ch = await resolve_channel(guild, "appeal_channel", ["appeals", "appeal"], "appeals")
    return ch


async def _warn_roles(guild: discord.Guild):
    """Get or create the Warn 1/2/3 roles (bot needs Manage Roles)."""
    roles = []
    for name in WARN_ROLE_NAMES:
        role = discord.utils.get(guild.roles, name=name)
        if role is None:
            try:
                role = await guild.create_role(name=name, colour=discord.Colour.orange(),
                                               reason="NEWR Support warn ladder")
            except Exception:
                role = None
        roles.append(role)
    return roles


async def send_appeal_dm(user, kind: str, ref_id: int, reason: str,
                         moderator_name: str) -> bool:
    """DM a punished user: what happened + an appeal button. Best-effort."""
    kind_text = {"warn": "warn", "mute": "mute", "ban": "ban"}.get(kind, kind)
    embed = discord.Embed(
        title=f"You received a {kind_text} in NEWR LABS",
        description=(f"**Reason:** {reason}\n**By:** {moderator_name}\n\n"
                     "If you feel this is wrong, you can submit an appeal "
                     "with the button below. Staff will review it."),
        colour=0xED4245)
    try:
        await user.send(embed=embed, view=AppealView(kind, ref_id, user.id))
        return True
    except Exception:
        return False


async def apply_warn(guild: discord.Guild, target_id: int, moderator,
                     reason: str):
    """Next warn level for target. Returns (level, warn_id, user_obj)."""
    level = count_warns(guild.id, target_id) + 1
    wid = db.add_row("warns", guild_id=guild.id, user_id=target_id,
                     moderator_id=moderator.id if moderator else 0,
                     reason=reason, created_at=db.now())
    target = await _member_or_user(guild, target_id)
    if isinstance(target, discord.Member):
        roles = await _warn_roles(guild)
        try:
            old = [r for r in target.roles if r.name in WARN_ROLE_NAMES]
            if old:
                await target.remove_roles(*old, reason="Warn ladder naik level")
            if level <= 3 and roles[level - 1] is not None:
                await target.add_roles(roles[level - 1], reason=f"Warn {level}")
        except Exception:
            pass
    if target is not None:
        await log_action(guild, "Warned", target, moderator, reason,
                         extra=f"Warn level {level}")
        dm_reason = reason
        if level >= 3 and isinstance(target, discord.Member):
            # Warn 3 = otomatis mute 24 jam (disetujui user 2026-10-31).
            try:
                await target.timeout(timedelta(minutes=1440),
                                     reason="Warn 3: auto-mute 24 hours")
                await log_action(guild, "Muted", target, moderator, reason,
                                 extra="Automatic because of Warn 3 (24 hours)")
                dm_reason = reason + " — Warn 3, auto-muted for 24 hours."
            except Exception:
                pass
        await send_appeal_dm(target, "warn", wid, dm_reason,
                             str(moderator) if moderator else "Staff")
    return level, wid, target


async def apply_mute(guild: discord.Guild, target_id: int, moderator,
                     reason: str, minutes: int) -> bool:
    target = await _member_or_user(guild, target_id)
    if not isinstance(target, discord.Member):
        return False
    try:
        await target.timeout(timedelta(minutes=minutes), reason=reason)
    except Exception:
        return False
    await log_action(guild, "Muted", target, moderator, reason,
                     extra=f"Durasi: {minutes} menit")
    await send_appeal_dm(target, "mute", 0, reason,
                         str(moderator) if moderator else "Staff")
    return True


async def apply_ban(guild: discord.Guild, target_id: int, moderator,
                    reason: str) -> bool:
    target = await _member_or_user(guild, target_id)
    # DM BEFORE the ban: after a ban the user cannot use /appeal.
    if target is not None:
        await send_appeal_dm(target, "ban", 0, reason,
                             str(moderator) if moderator else "Staff")
    try:
        user = target if target is not None else await guild.fetch_user(target_id)
        await guild.ban(user, reason=reason, delete_message_days=0)
    except Exception:
        return False
    if target is not None:
        await log_action(guild, "Banned", target, moderator, reason)
    return True


async def _close_report_message(interaction: discord.Interaction, status_text: str):
    """Replace the report buttons with a closed status line."""
    try:
        msg = interaction.message
        embed = discord.Embed.from_dict(msg.embeds[0].to_dict()) if msg.embeds else discord.Embed()
        embed.add_field(name="Status", value=status_text, inline=False)
        await interaction.response.edit_message(embed=embed, view=None)
    except Exception:
        try:
            await interaction.response.send_message(status_text, ephemeral=True)
        except Exception:
            pass


def _staff_check(interaction: discord.Interaction) -> bool:
    return isinstance(interaction.user, discord.Member) and is_staff(interaction.user)


# ---------- appeal: DM button + modal + staff review ----------

class AppealView(discord.ui.View):
    def __init__(self, kind: str, ref_id: int, target_id: int):
        super().__init__(timeout=None)
        self.kind, self.ref_id, self.target_id = kind, ref_id, target_id
        btn = discord.ui.Button(label="Submit Appeal", style=discord.ButtonStyle.primary,
                                emoji="📝", custom_id=f"newr_appeal_{kind}_{ref_id}_{target_id}")
        btn.callback = self._open_modal
        self.add_item(btn)

    async def _open_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            AppealModal(self.kind, self.ref_id, self.target_id))


class AppealModal(discord.ui.Modal):
    def __init__(self, kind: str, ref_id: int, target_id: int):
        super().__init__(title="Submit Appeal",
                         custom_id=f"newr_appeal_modal_{kind}_{ref_id}_{target_id}")
        self.kind, self.ref_id, self.target_id = kind, ref_id, target_id
        self.explanation = discord.ui.TextInput(label="Why should this punishment be lifted?",
                                                style=discord.TextStyle.paragraph,
                                                required=True, max_length=1000)
        self.add_item(self.explanation)

    async def on_submit(self, interaction: discord.Interaction):
        # Banned users appeal from DM: no guild on the interaction, so
        # the guild is recovered from their open punishment record is
        # not possible here; instead the appeal is filed against every
        # guild the bot shares is wrong. Use the DM view's guild hint:
        # appeals from DM carry the guild via the stored report/appeal
        # lookup below (warn ref -> warns table, else first guild).
        guild = interaction.guild
        if guild is None:
            # Find the guild from the warn record, or fall back to the
            # bot's first guild (single-server bot: NEWR LABS).
            guild = None
            if self.kind == "warn" and self.ref_id:
                with db._conn() as conn:
                    row = conn.execute("SELECT guild_id FROM warns WHERE id=?",
                                       (self.ref_id,)).fetchone()
                if row and interaction.client.get_guild(row["guild_id"]):
                    guild = interaction.client.get_guild(row["guild_id"])
            if guild is None and interaction.client.guilds:
                guild = interaction.client.guilds[0]
        if guild is None:
            await interaction.response.send_message("Appeal failed to send: server not found.",
                                                    ephemeral=True)
            return
        aid = db.add_row("appeals", guild_id=guild.id, author_id=interaction.user.id,
                         text=str(self.explanation), created_at=db.now(),
                         kind=self.kind, ref_id=self.ref_id, status="open",
                         target_id=self.target_id)
        channel = await resolve_appeal_channel(guild)
        embed = discord.Embed(
            title=f"📝 Appeal #{aid} — {self.kind}",
            description=(f"**User:** <@{self.target_id}> (ID {self.target_id})\n"
                         f"**Explanation:** {self.explanation}"),
            colour=0x5865F2)
        if channel is not None:
            try:
                msg = await channel.send(embed=embed,
                                   view=AppealReviewView(aid, self.target_id, self.kind))
                with db._conn() as conn:
                    conn.execute("UPDATE appeals SET message_id=?, channel_id=? WHERE id=?",
                                 (msg.id, channel.id, aid))
            except Exception:
                pass
        await interaction.response.send_message(
            f"Appeal #{aid} submitted. Staff will review it.", ephemeral=True)


class AppealReviewView(discord.ui.View):
    def __init__(self, appeal_id: int, target_id: int, kind: str):
        super().__init__(timeout=None)
        self.appeal_id, self.target_id, self.kind = appeal_id, target_id, kind
        for label, style, suffix in [("Accept Appeal", discord.ButtonStyle.success, "accept"),
                                     ("Reject Appeal", discord.ButtonStyle.danger, "reject")]:
            btn = discord.ui.Button(label=label, style=style,
                                    custom_id=f"newr_appeal_{suffix}_{appeal_id}")
            btn.callback = self._accept if suffix == "accept" else self._reject
            self.add_item(btn)

    async def _decide(self, interaction: discord.Interaction, accepted: bool):
        if not _staff_check(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True)
            return
        guild = interaction.guild
        with db._conn() as conn:
            conn.execute("UPDATE appeals SET status=? WHERE id=?",
                         ("accepted" if accepted else "rejected", self.appeal_id))
        if accepted and guild is not None:
            target = await _member_or_user(guild, self.target_id)
            # kind='general' (from /appeal): no specific punishment to
            # remove automatically; staff handle it manually after accept.
            try:
                if self.kind == "warn":
                    with db._conn() as conn:
                        conn.execute("DELETE FROM warns WHERE guild_id=? AND user_id=?",
                                     (guild.id, self.target_id))
                    if isinstance(target, discord.Member):
                        old = [r for r in target.roles if r.name in WARN_ROLE_NAMES]
                        if old:
                            await target.remove_roles(*old, reason="Appeal diterima")
                elif self.kind == "mute" and isinstance(target, discord.Member):
                    await target.timeout(None, reason="Appeal diterima")
                elif self.kind == "ban":
                    user = target if target is not None else await guild.fetch_user(self.target_id)
                    await guild.unban(user, reason="Appeal diterima")
            except Exception:
                pass
            if target is not None:
                try:
                    if self.kind in ("warn", "mute", "ban"):
                        await target.send(f"Your appeal in NEWR LABS was **accepted**. "
                                          f"Your {self.kind} punishment has been lifted.")
                    else:
                        await target.send("Your appeal in NEWR LABS was **accepted** by staff.")
                except Exception:
                    pass
        else:
            target = None
            if guild is not None:
                target = await _member_or_user(guild, self.target_id)
            if target is not None:
                try:
                    await target.send(f"Your appeal in NEWR LABS was **rejected** by staff.")
                except Exception:
                    pass
        try:
            msg = interaction.message
            embed = discord.Embed.from_dict(msg.embeds[0].to_dict()) if msg.embeds else discord.Embed()
            embed.add_field(name="Appeal Result",
                            value=("Accepted by " + interaction.user.mention) if accepted
                            else ("Rejected by " + interaction.user.mention), inline=False)
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception:
            await interaction.response.send_message("Appeal decision saved.", ephemeral=True)


    async def _accept(self, interaction: discord.Interaction):
        await self._decide(interaction, True)

    async def _reject(self, interaction: discord.Interaction):
        await self._decide(interaction, False)


# ---------- report staff buttons ----------

class ReportView(discord.ui.View):
    def __init__(self, report_id: int, target_id: int, reporter_id: int, next_warn: int):
        super().__init__(timeout=None)
        self.report_id, self.target_id, self.reporter_id = report_id, target_id, reporter_id
        self.next_warn = next_warn
        warn_btn = discord.ui.Button(
            label=f"Warn {next_warn}" if next_warn <= 3 else "Warn (Maximum)",
            style=discord.ButtonStyle.primary, emoji="⚠️",
            custom_id=f"newr_report_warn_{report_id}",
            disabled=next_warn > 3)
        warn_btn.callback = self._warn
        self.add_item(warn_btn)
        for label, style, emoji, suffix, cb in [
                ("Mute", discord.ButtonStyle.secondary, "🔇", "mute", self._mute_menu),
                ("Ban", discord.ButtonStyle.danger, "🔨", "ban", self._ban_menu),
                ("False Report", discord.ButtonStyle.secondary, "🚫", "false", self._false),
                ("Not Guilty", discord.ButtonStyle.success, "✅", "innocent", self._innocent),
                ("Close", discord.ButtonStyle.secondary, "✖️", "close", self._close)]:
            btn = discord.ui.Button(label=label, style=style, emoji=emoji,
                                    custom_id=f"newr_report_{suffix}_{report_id}")
            btn.callback = cb
            self.add_item(btn)

    def _report(self):
        return get_report(self.report_id)

    async def _warn(self, interaction: discord.Interaction):
        if not _staff_check(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True)
            return
        row = self._report()
        if row is None or (row["status"] not in (None, "open")):
            await interaction.response.send_message("This report is already closed.", ephemeral=True)
            return
        level, _, _ = await apply_warn(interaction.guild, self.target_id, interaction.user,
                                       f"From report #{self.report_id}: {row['reason']}")
        mark_report(self.report_id, "closed", f"warn {level}")
        await _close_report_message(
            interaction, f"Warn {level} given by {interaction.user.mention}."
            + (" Auto-muted for 24 hours (Warn 3)." if level >= 3 else ""))

    async def _mute_menu(self, interaction: discord.Interaction):
        if not _staff_check(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True)
            return
        await interaction.response.edit_message(
            view=MuteDurationView(self.report_id, self.target_id))

    async def _ban_menu(self, interaction: discord.Interaction):
        if not _staff_check(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True)
            return
        await interaction.response.edit_message(view=BanConfirmView(self.report_id, self.target_id))

    async def _false(self, interaction: discord.Interaction):
        if not _staff_check(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True)
            return
        row = self._report()
        if row is None or (row["status"] not in (None, "open")):
            await interaction.response.send_message("This report is already closed.", ephemeral=True)
            return
        # Consequence for the reporter: the next warn level, same ladder.
        level, _, _ = await apply_warn(interaction.guild, self.reporter_id, interaction.user,
                                       f"False report (report #{self.report_id})")
        mark_report(self.report_id, "false", f"reporter warn {level}")
        await _close_report_message(
            interaction,
            f"Report declared false by {interaction.user.mention}. "
            f"Reporter received Warn {level}.")

    async def _innocent(self, interaction: discord.Interaction):
        """Target dinyatakan tidak bersalah: report ditandai bersih.

        Report TIDAK dihapus (jejak audit tetap ada), tapi statusnya
        jadi 'innocent', sehingga di /report_list tidak lagi tampil
        sebagai tuduhan terbuka dan tidak dihitung sebagai riwayat
        buruk target di report berikutnya.
        """
        if not _staff_check(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True)
            return
        row = self._report()
        if row is None or (row["status"] not in (None, "open")):
            await interaction.response.send_message("This report is already closed.", ephemeral=True)
            return
        mark_report(self.report_id, "innocent", "innocent")
        await _close_report_message(
            interaction,
            f"Declared not guilty by {interaction.user.mention}. "
            "This report is marked clean in the report list.")

    async def _close(self, interaction: discord.Interaction):
        if not _staff_check(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True)
            return
        mark_report(self.report_id, "closed", "dismissed")
        await _close_report_message(
            interaction, f"Closed without action by {interaction.user.mention}.")


class MuteDurationView(discord.ui.View):
    def __init__(self, report_id: int, target_id: int):
        super().__init__(timeout=None)
        self.report_id, self.target_id = report_id, target_id
        for minutes, label in MUTE_DURATIONS:
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary,
                                    custom_id=f"newr_report_mute_{report_id}_{minutes}")
            async def _cb(interaction: discord.Interaction, minutes=minutes):
                await self._apply(interaction, minutes)
            btn.callback = _cb
            self.add_item(btn)

    async def _apply(self, interaction: discord.Interaction, minutes: int):
        if not _staff_check(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True)
            return
        row = get_report(self.report_id)
        if row is None or (row["status"] not in (None, "open")):
            await interaction.response.send_message("This report is already closed.", ephemeral=True)
            return
        ok = await apply_mute(interaction.guild, self.target_id, interaction.user,
                              f"From report #{self.report_id}: {row['reason']}", minutes)
        if not ok:
            await interaction.response.send_message("Mute failed: user is not in the server.",
                                                    ephemeral=True)
            return
        mark_report(self.report_id, "closed", f"mute {minutes}m")
        await _close_report_message(
            interaction, f"Muted for {minutes} minutes by {interaction.user.mention}.")


class BanConfirmView(discord.ui.View):
    def __init__(self, report_id: int, target_id: int):
        super().__init__(timeout=None)
        self.report_id, self.target_id = report_id, target_id
        yes = discord.ui.Button(label="Yes, Ban", style=discord.ButtonStyle.danger,
                                custom_id=f"newr_report_banconfirm_{report_id}")
        yes.callback = self._ban
        self.add_item(yes)
        no = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary,
                               custom_id=f"newr_report_bancancel_{report_id}")
        no.callback = self._cancel
        self.add_item(no)

    async def _ban(self, interaction: discord.Interaction):
        if not _staff_check(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True)
            return
        row = get_report(self.report_id)
        if row is None or (row["status"] not in (None, "open")):
            await interaction.response.send_message("This report is already closed.", ephemeral=True)
            return
        ok = await apply_ban(interaction.guild, self.target_id, interaction.user,
                             f"From report #{self.report_id}: {row['reason']}")
        if not ok:
            await interaction.response.send_message("Ban failed.", ephemeral=True)
            return
        mark_report(self.report_id, "closed", "ban")
        await _close_report_message(
            interaction, f"Banned by {interaction.user.mention}.")

    async def _cancel(self, interaction: discord.Interaction):
        if not _staff_check(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True)
            return
        row = get_report(self.report_id)
        next_warn = count_warns(interaction.guild.id, self.target_id) + 1 if row else 1
        await interaction.response.edit_message(
            view=ReportView(self.report_id, self.target_id,
                            row["reporter_id"] if row else 0, next_warn))


async def post_report_embed(guild: discord.Guild, report_id: int, target_id: int,
                            reporter_id: int, category: str, reason: str,
                            evidence_url: str | None = None):
    """Post one report to the report channel, with staff buttons."""
    channel = await resolve_report_channel(guild)
    if channel is None:
        return None
    next_warn = count_warns(guild.id, target_id) + 1
    prev_reports = count_open_reports(guild.id, target_id)
    emoji = CATEGORY_EMOJI.get(category, "🟡")
    embed = discord.Embed(
        title=f"{emoji} Report #{report_id} — {category}",
        description=(f"**Target:** <@{target_id}> (ID {target_id})\n"
                     f"**Reporter:** <@{reporter_id}> (ID {reporter_id})\n"
                     f"**Reason:** {reason}\n"
                     f"**Target history:** {next_warn - 1} previous warns, "
                     f"{max(0, prev_reports - 1)} other open reports\n\n"
                     "⚠️ Do not report people arbitrarily: false reports "
                     "can result in a warn/mute for the reporter."),
        colour=0xED4245 if category == "Severe" else 0xFEE75C if category == "Medium" else 0x57F287)
    if evidence_url:
        embed.set_image(url=evidence_url)
    try:
        msg = await channel.send(
            embed=embed, view=ReportView(report_id, target_id, reporter_id, next_warn))
        with db._conn() as conn:
            conn.execute("UPDATE reports SET message_id=?, channel_id=? WHERE id=?",
                         (msg.id, channel.id, report_id))
        return msg
    except Exception:
        return None


class ReportFlow(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReportFlow(bot))
    # Re-register buttons for still-open cases, so they survive restarts.
    try:
        db.init_db()
        with db._conn() as conn:
            for row in conn.execute(
                    "SELECT * FROM reports WHERE status IS NULL OR status='open'"):
                try:
                    bot.add_view(ReportView(row["id"], row["target_id"], row["reporter_id"],
                                            count_warns(row["guild_id"], row["target_id"]) + 1))
                except Exception:
                    pass
            for row in conn.execute(
                    "SELECT * FROM appeals WHERE status='open'"):
                try:
                    bot.add_view(AppealReviewView(row["id"], row["target_id"] or row["author_id"],
                                                  row["kind"] or "warn"))
                except Exception:
                    pass
    except Exception:
        pass
