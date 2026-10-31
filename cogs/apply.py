"""Staff application system (Appy-style, built into NEWR Support).

Appy in the old setup was a separate bot: a panel in #job-application,
a form, submissions posted to a staff channel, staff Accept/Deny
(with reason), History, and Open Ticket. This cog replaces that
with the same flow, plus a few improvements:

- One application open at a time per user (Appy allowed duplicates).
- The submission is never public: it goes only to the staff-only
  #apply channel (resolved from the apply_channel setting, else a
  channel named "apply"), never to #job-application itself.
- Accept assigns the applied role automatically when the position
  matches an existing role name (e.g. "Moderator" -> "⚔️ Moderator");
  Admin/Executive acceptances require owner/administrator, so a
  moderator cannot hand out Admin.
- History button shows the applicant's warns, past applications,
  and open reports, so staff decide with context.
- Open Ticket button creates a private ticket channel with the
  applicant (like Appy's), for follow-up questions.
- All decisions DM the applicant and are recorded in the
  applications table (status, reviewer, reason), so /backup
  includes them.

No slash command is needed: the panel button, modal, and review
buttons are all persistent views (stable custom_ids), registered
in bot.py setup_hook for open applications, so they survive
restarts. The panel itself is posted once to #job-application.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import discord
from cogs.emoji import partial
from cogs.ui import denied as _denied
from discord import app_commands
from discord.ext import commands

import db
from roles import is_staff, support_roles

EMBED_COLOR = 0x5865F2


def _wib(iso: str | None) -> str:
    """ISO UTC timestamp -> 'Saturday, 31 October 2026, 11:58 WIB'.

    Returns '-' when the timestamp is missing or unparseable, so
    a missing timestamp never breaks an embed.
    """
    if not iso:
        return "-"
    try:
        from zoneinfo import ZoneInfo
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        wib = dt.astimezone(ZoneInfo("Asia/Jakarta"))
        return wib.strftime("%A, %d %B %Y, %H:%M WIB")
    except Exception:
        return str(iso)


def _finish_embed(embed: discord.Embed, status_label: str, decision_text: str,
                  opened_iso: str | None, closed_iso: str) -> discord.Embed:
    """Update a posted application embed in place (shared by
    accept/deny and by /apply close, so the three can never drift).

    - The 'Status' field is REPLACED (it used to be left as 'Open'
      forever, which is why accepted applications still looked open).
    - A 'Decision' field is added/replaced, always stating the role
      outcome: assigned role, or explicitly 'no role assigned' when
      the position matched no role (e.g. 'Mod' vs 'Moderator').
    - 'Opened' and 'Closed' timestamp fields are added/replaced.
    """
    fields = [(f.name, f.value, f.inline) for f in embed.fields]
    out: list[tuple[str, str, bool]] = []
    seen_status = seen_decision = seen_opened = seen_closed = False
    for name, value, inline in fields:
        low = name.lower()
        if "status" in low:
            out.append((name, status_label, inline)); seen_status = True
        elif "decision" in low:
            out.append((name, decision_text, inline)); seen_decision = True
        elif "opened" in low:
            out.append((name, _wib(opened_iso), inline)); seen_opened = True
        elif "closed" in low:
            out.append((name, _wib(closed_iso), inline)); seen_closed = True
        else:
            out.append((name, value, inline))
    if not seen_status:
        out.append(("🟢 Status", status_label, True))
    if not seen_decision:
        out.append(("Decision", decision_text, False))
    if not seen_opened:
        out.append(("🕐 Opened", _wib(opened_iso), True))
    if not seen_closed:
        out.append(("🕐 Closed", _wib(closed_iso), True))
    embed.clear_fields()
    for name, value, inline in out:
        embed.add_field(name=name, value=value, inline=inline)
    return embed


def _apply_channel(guild: discord.Guild) -> discord.TextChannel | None:
    ch_id = db.get_setting(guild.id, "apply_channel", "0")
    if ch_id and ch_id != "0":
        ch = guild.get_channel(int(ch_id))
        if isinstance(ch, discord.TextChannel):
            return ch
    ch = discord.utils.get(guild.text_channels, name="apply")
    return ch if isinstance(ch, discord.TextChannel) else None


DEFAULT_POSITIONS = ["Moderator", "Helper", "Admin"]


def _get_positions(guild_id: int) -> list[str]:
    """Customizable position list for applications.

    Seeded once per guild with Moderator/Helper/Admin, then fully
    staff-customizable via /apply position-add / position-remove:
    the list is NOT limited to staff/mod/admin, any position name
    can be added, and defaults can be removed.
    """
    with db._conn() as conn:
        rows = conn.execute("SELECT position FROM apply_positions WHERE guild_id=? ORDER BY position",
                            (guild_id,)).fetchall()
        if not rows:
            for pos in DEFAULT_POSITIONS:
                conn.execute("INSERT OR IGNORE INTO apply_positions VALUES (?, ?)", (guild_id, pos))
            return list(DEFAULT_POSITIONS)
        return [r["position"] for r in rows]


class PositionSelectView(discord.ui.View):
    """Step before the form: pick a position, or Custom.

    Shown by /apply submit and by the panel Apply button, so an
    applicant always sees what positions are open (option 1, 2, ...)
    instead of guessing. Picking a position opens the same modal
    with that position prefilled; Custom opens it blank for a
    free-text position.
    """
    def __init__(self, guild_id: int) -> None:
        super().__init__(timeout=180)
        positions = _get_positions(guild_id)[:24]  # Discord select cap is 25
        options = [discord.SelectOption(label=pos, value=pos) for pos in positions]
        options.append(discord.SelectOption(label="Custom position...",
                                            value="__custom__",
                                            description="Type your own position in the form"))
        select = discord.ui.Select(placeholder="Choose a position to apply for",
                                   options=options)

        async def _choose(interaction: discord.Interaction):
            chosen = select.values[0]
            await interaction.response.send_modal(
                ApplyModal(position_default="" if chosen == "__custom__" else chosen))

        select.callback = _choose
        self.add_item(select)


def _match_role(guild: discord.Guild, position: str) -> discord.Role | None:
    """Find a role whose name matches the applied position.

    "Moderator" matches "⚔️ Moderator"; "Admin" matches "⭐ Admin".
    Exact (emoji-stripped) match ONLY. There used to be a
    contains-match fallback that preferred the highest-positioned
    role, which was a privilege bug: applying for "Mod" matched
    both "Moderator" and "Senior Mod" and auto-assigned the higher
    "Senior Mod" role. An ambiguous abbreviation now assigns no
    role at all (staff can assign the right role manually), which
    is safe, instead of silently escalating the applicant.
    """
    pos = position.strip().lower()
    if not pos:
        return None

    def clean(name: str) -> str:
        return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()

    clean_pos = clean(pos)
    exact = [r for r in guild.roles if clean(r.name) == clean_pos]
    if exact:
        return sorted(exact, key=lambda r: r.position, reverse=True)[0]
    return None


class ApplyModal(discord.ui.Modal, title="Staff Application"):
    position = discord.ui.TextInput(label="Position you are applying for",
                                    placeholder="e.g. Moderator, Helper, Admin",
                                    max_length=100)

    def __init__(self, position_default: str = "") -> None:
        super().__init__()
        if position_default:
            self.position.default = position_default
    experience = discord.ui.TextInput(label="Experience / skills",
                                      style=discord.TextStyle.paragraph,
                                      max_length=1000)
    reason = discord.ui.TextInput(label="Why do you want this role?",
                                  style=discord.TextStyle.paragraph,
                                  max_length=1000)
    availability = discord.ui.TextInput(label="Availability / timezone (optional)",
                                        required=False, max_length=200)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        with db._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM applications WHERE guild_id=? AND user_id=? AND status='open'",
                (guild.id, interaction.user.id)).fetchone()
        if existing:
            await interaction.response.send_message(
                f"You already have an open application (#{existing['id']}). "
                f"Please wait for staff to review it before applying again.",
                ephemeral=True)
            return
        aid = await _post_application(guild, interaction.user, str(self.position),
                                      str(self.experience), str(self.reason), str(self.availability))
        await interaction.response.send_message(
            f"Application #{aid} submitted for **{self.position}**. "
            f"Staff will review it and DM you the result.", ephemeral=True)


async def _post_application(guild: discord.Guild, user, position: str, experience: str,
                            reason: str, availability: str) -> int:
    """Create the application row and post it to #apply with the
    review view and staff ping. Shared by the modal flow and the
    saul-jb-style DM flow, so the two can never drift apart."""
    opened = db.now()
    aid = db.add_row("applications", guild_id=guild.id, user_id=user.id,
                     position=position, experience=experience, reason=reason,
                     availability=availability, status="open", created_at=opened)
    channel = _apply_channel(guild)
    from cogs.ui import make as _make
    embed = _make(f"📝 Application #{aid} — {position}",
                  fields=[("👤 Applicant", f"{user.mention} (ID {user.id})", True),
                          ("🎯 Position", position, True),
                          ("🟢 Status", "Open — awaiting staff review", True),
                          ("🕐 Opened", _wib(opened), True),
                          ("💼 Experience", experience, False),
                          ("💬 Why", reason, False),
                          ("🕐 Availability", availability or "-", False)])
    if channel is not None:
        try:
            from roles import roles_in_categories
            staff = roles_in_categories(guild, "support") or roles_in_categories(guild, "moderator")
            pings = " ".join(r.mention for r in staff) if staff else ""
            msg = await channel.send(content=pings or None, embed=embed, view=ApplyReviewView(aid))
            with db._conn() as conn:
                conn.execute("UPDATE applications SET message_id=?, channel_id=? WHERE id=?",
                             (msg.id, channel.id, aid))
        except Exception:
            pass
    return aid


# saul-jb-style DM application: the same 4 questions, asked one
# by one in DM instead of in a modal. Type "cancel" at any step
# to stop; answers are only submitted at the last step.
DM_QUESTIONS = [
    ("position", "Question 1/4 — What position are you applying for? (e.g. Moderator, Helper, Admin)"),
    ("experience", "Question 2/4 — What is your experience / skills?"),
    ("reason", "Question 3/4 — Why do you want this role?"),
    ("availability", "Question 4/4 — What is your availability / timezone? (you can type 'skip')"),
]


class ApplyPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Apply", style=discord.ButtonStyle.primary,
                       emoji=partial("newr_apply"), custom_id="newr_apply_panel")
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        await interaction.response.send_message(
            "Choose a position to apply for:", view=PositionSelectView(interaction.guild.id),
            ephemeral=True)

    @discord.ui.button(label="Apply via DM", style=discord.ButtonStyle.secondary,
                       emoji=partial("newr_chat"), custom_id="newr_apply_dm_panel")
    async def apply_dm(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        guild = interaction.guild
        with db._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM applications WHERE guild_id=? AND user_id=? AND status='open'",
                (guild.id, interaction.user.id)).fetchone()
        if existing:
            await interaction.response.send_message(
                f"You already have an open application (#{existing['id']}).", ephemeral=True); return
        with db._conn() as conn:
            conn.execute(
                "INSERT INTO dm_applications VALUES (?, ?, 0, '', '', '', '', ?) "
                "ON CONFLICT(user_id, guild_id) DO UPDATE SET step=0, position='', experience='', reason='', availability=''",
                (interaction.user.id, guild.id, db.now()))
        try:
            await interaction.user.send(
                "📝 NEWR LABS application — I will ask you 4 questions, one at a time. "
                "Type 'cancel' at any point to stop.\n\n" + DM_QUESTIONS[0][1])
        except discord.HTTPException:
            await interaction.response.send_message(
                "I could not DM you — your DMs are closed. Please open DMs and try again, "
                "or use Apply (modal) instead.", ephemeral=True); return
        await interaction.response.send_message(
            "Check your DMs: I started your application there.", ephemeral=True)


class ApplyDMListener(commands.Cog):
    """Collects DM answers for the saul-jb-style DM application."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is not None:
            return
        with db._conn() as conn:
            state = conn.execute("SELECT * FROM dm_applications WHERE user_id=?",
                                 (message.author.id,)).fetchone()
        if state is None:
            return
        # Image-captcha DM replies are handled by the security cog;
        # this listener only runs when a DM application is in progress.
        # (If both were active, the captcha check runs first in the
        # security cog and this listener still sees the message, so
        # guard: a captcha code is 5 uppercase/digits and is not a
        # valid position/experience answer, but to avoid mixing the
        # two flows, a DM application answer that is exactly a
        # stored captcha code is ignored here.)
        with db._conn() as conn:
            captcha = conn.execute("SELECT code FROM image_captchas WHERE user_id=?",
                                   (message.author.id,)).fetchone()
        if captcha and message.content.strip().upper() == captcha["code"].upper():
            return
        text = message.content.strip()
        if text.lower() == "cancel":
            with db._conn() as conn:
                conn.execute("DELETE FROM dm_applications WHERE user_id=?", (message.author.id,))
            await message.channel.send("Application cancelled. You can start again from the panel anytime.")
            return
        step = state["step"]
        field = DM_QUESTIONS[step][0]
        value = "" if (field == "availability" and text.lower() == "skip") else text
        with db._conn() as conn:
            conn.execute(f"UPDATE dm_applications SET {field}=?, step=step+1 WHERE user_id=?",
                         (value, message.author.id))
            new_state = conn.execute("SELECT * FROM dm_applications WHERE user_id=?",
                                     (message.author.id,)).fetchone()
        if new_state["step"] >= len(DM_QUESTIONS):
            guild = self.bot.get_guild(new_state["guild_id"])
            with db._conn() as conn:
                conn.execute("DELETE FROM dm_applications WHERE user_id=?", (message.author.id,))
            if guild is None:
                await message.channel.send("Server not found. Please try again in the server.")
                return
            member = guild.get_member(message.author.id)
            if member is None:
                await message.channel.send("You are not in the server anymore.")
                return
            aid = await _post_application(guild, member, new_state["position"],
                                          new_state["experience"], new_state["reason"],
                                          new_state["availability"])
            await message.channel.send(
                f"✅ Application #{aid} submitted for **{new_state['position']}**. "
                f"Staff will review it and DM you the result.")
        else:
            await message.channel.send(DM_QUESTIONS[new_state["step"]][1])


class ApplyDecisionModal(discord.ui.Modal):
    def __init__(self, application_id: int, decision: str) -> None:
        super().__init__(title=f"{decision.capitalize()} Application")
        self.application_id, self.decision = application_id, decision
        self.reason_input = discord.ui.TextInput(
            label="Reason (optional)", style=discord.TextStyle.paragraph,
            required=False, max_length=500)
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await _decide(interaction, self.application_id, self.decision,
                      str(self.reason_input) or "")


async def _decide(interaction: discord.Interaction, application_id: int,
                  decision: str, reason: str) -> None:
    guild = interaction.guild
    if not is_staff(interaction.user):  # type: ignore[arg-type]
        await interaction.response.send_message(embed=_denied(), ephemeral=True); return
    with db._conn() as conn:
        row = conn.execute("SELECT * FROM applications WHERE id=? AND guild_id=?",
                           (application_id, guild.id)).fetchone()
    if row is None:
        await interaction.response.send_message("Application not found.", ephemeral=True); return
    if row["status"] != "open":
        await interaction.response.send_message(
            f"This application is already {row['status']}.", ephemeral=True); return
    applicant = guild.get_member(row["user_id"])
    assigned_role = None
    if decision == "accept":
        role = _match_role(guild, row["position"])
        if role is not None and role.name.lower() in ("admin", "⭐ admin", "executive", "🏛️ executive"):
            # High roles need owner/administrator, not just any staff.
            if guild.owner_id != interaction.user.id and not interaction.user.guild_permissions.administrator:  # type: ignore[attr-defined]
                await interaction.response.send_message(
                    "Only the server owner or an administrator can accept "
                    "Admin/Executive applications.", ephemeral=True); return
        if role is not None and applicant is not None:
            try:
                await applicant.add_roles(role, reason=f"Application #{application_id} accepted")
                assigned_role = role.name
            except discord.HTTPException:
                pass
    closed = db.now()
    with db._conn() as conn:
        conn.execute(
            "UPDATE applications SET status=?, reviewer_id=?, review_reason=?, closed_at=? WHERE id=?",
            ("accepted" if decision == "accept" else "rejected",
             interaction.user.id, reason, closed, application_id))
    # Role outcome is always stated: a missing 'role assigned' line
    # used to look like the decision never assigned anything, when
    # in fact the position simply matched no role (e.g. 'Mod').
    if decision == "accept":
        role_text = (f" — role assigned: {assigned_role}" if assigned_role
                     else f" — no role assigned (position '{row['position']}' "
                          f"did not match a role; staff can assign it manually)")
    else:
        role_text = ""
    decision_text = (f"{'Accepted' if decision == 'accept' else 'Rejected'} by "
                     f"{interaction.user.mention}"
                     + (f" — {reason}" if reason else "") + role_text)
    # Close the review message: remove buttons, update Status in
    # place (not just append a Decision field), add timestamps.
    try:
        msg = interaction.message
        if msg is not None and msg.embeds:
            embed = _finish_embed(
                msg.embeds[0],
                "Accepted" if decision == "accept" else "Rejected",
                decision_text, row["created_at"], closed)
            await msg.edit(embed=embed, view=None)
    except Exception:
        pass
    # DM the applicant the result.
    if applicant is not None:
        try:
            await applicant.send(
                f"Your staff application #{application_id} for **{row['position']}** in NEWR LABS was "
                f"**{'accepted' if decision == 'accept' else 'rejected'}** by staff"
                + (f" — {reason}" if reason else "")
                + (f". You have been given the {assigned_role} role." if assigned_role
                   else f". No role was assigned automatically (position '{row['position']}' "
                        f"did not match a role)." if decision == "accept" else "."))
        except discord.HTTPException:
            pass
    await interaction.response.send_message(
        f"Application #{application_id} {decision}ed"
        + (f" (role: {assigned_role})" if assigned_role else "") + ".",
        ephemeral=True)


async def _close_application(interaction: discord.Interaction, application_id: int,
                             reason: str) -> None:
    """Staff-only close of an OPEN application (no accept/deny).

    Shared embed update with _decide, so a closed application
    also shows Status 'Closed' plus Opened/Closed timestamps,
    and the applicant is DM'd. Already-decided applications
    cannot be closed this way.
    """
    guild = interaction.guild
    if not is_staff(interaction.user):  # type: ignore[arg-type]
        await interaction.response.send_message(embed=_denied(), ephemeral=True); return
    with db._conn() as conn:
        row = conn.execute("SELECT * FROM applications WHERE id=? AND guild_id=?",
                           (application_id, guild.id)).fetchone()
    if row is None:
        await interaction.response.send_message("Application not found.", ephemeral=True); return
    if row["status"] != "open":
        await interaction.response.send_message(
            f"This application is already {row['status']} and cannot be closed.", ephemeral=True); return
    closed = db.now()
    with db._conn() as conn:
        conn.execute(
            "UPDATE applications SET status='closed', reviewer_id=?, review_reason=?, closed_at=? WHERE id=?",
            (interaction.user.id, reason, closed, application_id))
    decision_text = (f"Closed by {interaction.user.mention}"
                     + (f" — {reason}" if reason else ""))
    # Edit the original #apply card if it still exists.
    try:
        channel = _apply_channel(guild)
        if channel is not None and row["message_id"]:
            msg = await channel.fetch_message(row["message_id"])
            if msg.embeds:
                embed = _finish_embed(msg.embeds[0], "Closed", decision_text,
                                      row["created_at"], closed)
                await msg.edit(embed=embed, view=None)
    except Exception:
        pass
    applicant = guild.get_member(row["user_id"])
    if applicant is not None:
        try:
            await applicant.send(
                f"Your staff application #{application_id} for **{row['position']}** in NEWR LABS was "
                f"closed by staff" + (f" — {reason}" if reason else "") + ".")
        except discord.HTTPException:
            pass
    await interaction.response.send_message(
        f"Application #{application_id} closed.", ephemeral=True)


class ApplyReviewView(discord.ui.View):
    """Appy's exact review bar, in Discord form.

    Appy: Accept, Deny, Accept with reason, Deny with reason, History,
    Open ticket with user, View submission on dashboard. The dashboard
    button becomes "View Submission" here: the full submission shown
    to staff in Discord (Appy's dashboard is a website this bot does
    not have; the data is identical).
    """
    def __init__(self, application_id: int) -> None:
        super().__init__(timeout=None)
        self.application_id = application_id
        buttons = [
            ("Accept", discord.ButtonStyle.success, "accept", self._accept_direct),
            ("Deny", discord.ButtonStyle.danger, "deny", self._deny_direct),
            ("Accept with reason", discord.ButtonStyle.success, "accept_reason", self._accept_reason),
            ("Deny with reason", discord.ButtonStyle.danger, "deny_reason", self._deny_reason),
            ("History", discord.ButtonStyle.secondary, "history", self._history),
            ("Open Ticket", discord.ButtonStyle.secondary, "ticket", self._ticket),
            ("View Submission", discord.ButtonStyle.secondary, "view", self._view),
        ]
        for label, style, suffix, cb in buttons:
            btn = discord.ui.Button(label=label, style=style,
                                    custom_id=f"newr_apply_{suffix}_{application_id}")
            btn.callback = cb
            self.add_item(btn)

    async def _accept_direct(self, interaction: discord.Interaction) -> None:
        await _decide(interaction, self.application_id, "accept", "")

    async def _deny_direct(self, interaction: discord.Interaction) -> None:
        await _decide(interaction, self.application_id, "deny", "")

    async def _accept_reason(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            ApplyDecisionModal(self.application_id, "accept"))

    async def _deny_reason(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(
            ApplyDecisionModal(self.application_id, "deny"))

    async def _view(self, interaction: discord.Interaction) -> None:
        if not is_staff(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            row = conn.execute("SELECT * FROM applications WHERE id=?",
                               (self.application_id,)).fetchone()
        if row is None:
            await interaction.response.send_message("Application not found.", ephemeral=True); return
        await interaction.response.send_message(
            f"**Application #{row['id']} — full submission**\n"
            f"Applicant: <@{row['user_id']}> (ID {row['user_id']})\n"
            f"Position: {row['position']}\n"
            f"Experience: {row['experience']}\n"
            f"Why: {row['reason']}\n"
            f"Availability: {row['availability'] or '-'}\n"
            f"Status: {row['status']}"
            + (f"\nReviewed by: <@{row['reviewer_id']}> — {row['review_reason'] or ''}" if row['reviewer_id'] else ""),
            ephemeral=True)

    async def _history(self, interaction: discord.Interaction) -> None:
        if not is_staff(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            row = conn.execute("SELECT * FROM applications WHERE id=?",
                               (self.application_id,)).fetchone()
            if row is None:
                await interaction.response.send_message("Application not found.", ephemeral=True); return
            uid, gid = row["user_id"], row["guild_id"]
            warns = conn.execute("SELECT COUNT(*) FROM warns WHERE guild_id=? AND user_id=?",
                                 (gid, uid)).fetchone()[0]
            past = conn.execute(
                "SELECT id, position, status FROM applications WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 10",
                (gid, uid)).fetchall()
            open_reports = conn.execute(
                "SELECT COUNT(*) FROM reports WHERE guild_id=? AND target_id=? AND status='open'",
                (gid, uid)).fetchone()[0]
        past_text = "\n".join(f"#{r['id']} {r['position']} — {r['status']}" for r in past) or "none"
        await interaction.response.send_message(
            f"**History for <@{uid}> (ID {uid})**\n"
            f"Warns: {warns}\nOpen reports against them: {open_reports}\n"
            f"Past applications:\n{past_text}", ephemeral=True)

    async def _ticket(self, interaction: discord.Interaction) -> None:
        if not is_staff(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            row = conn.execute("SELECT * FROM applications WHERE id=?",
                               (self.application_id,)).fetchone()
        if row is None:
            await interaction.response.send_message("Application not found.", ephemeral=True); return
        guild = interaction.guild
        applicant = guild.get_member(row["user_id"])
        if applicant is None:
            await interaction.response.send_message(
                "Applicant is not in the server, so a ticket cannot be opened.", ephemeral=True); return
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            applicant: discord.PermissionOverwrite(view_channel=True, send_messages=True,
                                                   read_message_history=True),
        }
        for role in support_roles(guild):
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True)
        import re as _re
        safe = _re.sub(r"[^a-z0-9_-]", "-", applicant.name.lower()) or "user"
        name = f"ticket-{safe}-apply-{self.application_id}"[:90].rstrip("-")
        try:
            channel = await guild.create_text_channel(
                name, overwrites=overwrites,
                topic=f"Application #{self.application_id} follow-up for {applicant}")
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Could not create a ticket: {e}", ephemeral=True); return
        await channel.send(
            f"{applicant.mention} Welcome! This ticket was opened from your staff application "
            f"#{self.application_id} so staff can ask follow-up questions.")
        await interaction.response.send_message(
            f"Ticket opened: {channel.mention}", ephemeral=True)


class ApplyCommands(commands.GroupCog, group_name="apply",
                    group_description="Staff applications (Appy-style)"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="submit", description="Submit a staff application (pick a position, then the form)")
    async def submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Choose a position to apply for:", view=PositionSelectView(interaction.guild.id),
            ephemeral=True)

    @app_commands.command(name="position-list", description="List customizable application positions (staff)")
    async def position_list(self, interaction: discord.Interaction):
        if not is_staff(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        positions = _get_positions(interaction.guild.id)
        text = "\n".join(f"{i + 1}. {pos}" for i, pos in enumerate(positions)) or "No positions."
        await interaction.response.send_message(
            f"**Application positions (applicants pick one, or Custom):**\n{text}\n\n"
            f"Change them with /apply position-add and /apply position-remove.",
            ephemeral=True)

    @app_commands.command(name="position-add", description="Add a position applicants can apply for (staff)")
    @app_commands.describe(position="Position name, e.g. Event Manager, Designer, Translator")
    async def position_add(self, interaction: discord.Interaction, position: str):
        if not is_staff(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        position = position.strip()
        if not position:
            await interaction.response.send_message("Position name cannot be empty.", ephemeral=True); return
        _get_positions(interaction.guild.id)  # seed defaults first
        with db._conn() as conn:
            conn.execute("INSERT OR IGNORE INTO apply_positions VALUES (?, ?)",
                         (interaction.guild.id, position))
        await interaction.response.send_message(
            f"Position **{position}** added. Applicants will now see it in /apply submit and the panel.",
            ephemeral=True)

    @app_commands.command(name="position-remove", description="Remove a position from applications (staff)")
    @app_commands.describe(position="Exact position name to remove")
    async def position_remove(self, interaction: discord.Interaction, position: str):
        if not is_staff(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            cur = conn.execute("DELETE FROM apply_positions WHERE guild_id=? AND position=?",
                               (interaction.guild.id, position.strip()))
            removed = cur.rowcount
        if removed:
            await interaction.response.send_message(f"Position **{position}** removed.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"Position **{position}** not found. Check it with /apply position-list.", ephemeral=True)

    @app_commands.command(name="list", description="List open applications (staff)")
    async def list_open(self, interaction: discord.Interaction):
        if not is_staff(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT id, user_id, position, created_at FROM applications "
                "WHERE guild_id=? AND status='open' ORDER BY id DESC LIMIT 20",
                (interaction.guild.id,)).fetchall()
        text = "\n".join(
            f"#{r['id']} <@{r['user_id']}> — {r['position']} ({r['created_at']})"
            for r in rows) or "No open applications."
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="show", description="Show an application in the staff #apply channel (staff)")
    @app_commands.describe(application_id="Application number, e.g. 3")
    async def show(self, interaction: discord.Interaction, application_id: int):
        if not is_staff(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            row = conn.execute("SELECT * FROM applications WHERE id=? AND guild_id=?",
                               (application_id, interaction.guild.id)).fetchone()
        if row is None:
            await interaction.response.send_message("Application not found.", ephemeral=True); return
        channel = _apply_channel(interaction.guild)
        if channel is None:
            await interaction.response.send_message("No #apply channel found.", ephemeral=True); return
        member = interaction.guild.get_member(row["user_id"])
        applicant_text = (f"{member.mention} (@{member.name})" if member
                          else f"<@{row['user_id']}> (ID {row['user_id']})")
        from cogs.ui import make as _make
        fields = [("👤 Applicant", applicant_text, True),
                  ("🎯 Position", row["position"], True),
                  ("🟢 Status", row["status"].capitalize(), True),
                  ("🕐 Opened", _wib(row["created_at"]), True)]
        if row["closed_at"]:
            fields.append(("🕐 Closed", _wib(row["closed_at"]), True))
        fields += [("💼 Experience", row["experience"], False),
                   ("💬 Why", row["reason"], False),
                   ("🕐 Availability", row["availability"] or "-", False)]
        if row["reviewer_id"]:
            fields.append(("Decision",
                           f"Reviewed by <@{row['reviewer_id']}>"
                           + (f" — {row['review_reason']}" if row["review_reason"] else ""),
                           False))
        embed = _make(f"📝 Application #{row['id']} — {row['position']}", fields=fields)
        try:
            from roles import roles_in_categories
            staff = roles_in_categories(interaction.guild, "support") or roles_in_categories(interaction.guild, "moderator")
            pings = " ".join(r.mention for r in staff) if staff else ""
            msg = await channel.send(content=pings or None, embed=embed,
                                     view=ApplyReviewView(row["id"]) if row["status"] == "open" else None)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Could not post to #apply: {e}", ephemeral=True); return
        await interaction.response.send_message(
            f"Application #{row['id']} shown in {channel.mention}: "
            f"https://discord.com/channels/{interaction.guild.id}/{channel.id}/{msg.id}",
            ephemeral=True)

    @app_commands.command(name="close", description="Close an open application without accept/deny (staff)")
    @app_commands.describe(application_id="Application number, e.g. 3", reason="Why it is being closed")
    async def close(self, interaction: discord.Interaction, application_id: int, reason: str = ""):
        await _close_application(interaction, application_id, reason)

    @app_commands.command(name="export", description="Export applications to CSV (staff, Appy-style)")
    async def export(self, interaction: discord.Interaction):
        if not is_staff(interaction.user):  # type: ignore[arg-type]
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        import csv, io as _io
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT id, user_id, position, experience, reason, availability, "
                "status, reviewer_id, review_reason, created_at, closed_at FROM applications "
                "WHERE guild_id=? ORDER BY id", (interaction.guild.id,)).fetchall()
        buf = _io.StringIO()
        w = csv.writer(buf)
        w.writerow(["id", "user_id", "position", "experience", "reason", "availability",
                    "status", "reviewer_id", "review_reason", "created_at", "closed_at"])
        for r in rows:
            w.writerow([r["id"], r["user_id"], r["position"], r["experience"], r["reason"],
                        r["availability"], r["status"], r["reviewer_id"], r["review_reason"],
                        r["created_at"], r["closed_at"]])
        await interaction.response.send_message(
            file=discord.File(_io.BytesIO(buf.getvalue().encode()), filename="applications.csv"),
            ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    # Panel + modal + review buttons are registered in bot.py; this
    # cog adds the /apply group (submit/list/export), which is one
    # top-level slot (traded for /uptime) with three subcommands.
    await bot.add_cog(ApplyCommands(bot))
    await bot.add_cog(ApplyDMListener(bot))
