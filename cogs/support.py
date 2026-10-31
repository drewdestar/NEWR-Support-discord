"""Support cog: tickets, FAQ, reports, suggestions, bugs, appeals, feedback."""
from __future__ import annotations

import io
import os
from datetime import datetime, timezone

import discord
from cogs.emoji import partial
from cogs.ui import denied as _denied
from discord import app_commands
from discord.ext import commands, tasks

import db
import smart
from roles import is_staff, support_roles

EMBED_COLOR = 0x5865F2



def _brain_note(interaction: discord.Interaction, kind: str, summary: str) -> None:
    """Record a Support event in the shared brain and notify NEWR AI.

    Best-effort only: a brain failure must never break a command.
    Never called with DM content (these are guild slash commands), and
    summaries are truncated; memory.py also redacts credential-like text.
    """
    try:
        import memory as brain
        user = interaction.user
        guild = interaction.guild
        roles = [r.name for r in getattr(user, "roles", [])] if guild else []
        brain.remember_user(str(user.id), str(guild.id) if guild else None,
                            getattr(user, "display_name", None) or str(user),
                            roles, source_bot="newr-support")
        brain.remember_event(str(guild.id) if guild else None, kind,
                             user_id=str(user.id), details=summary[:500],
                             source_bot="newr-support")
        brain.send_bot_message("newr-support", "newr-ai", "ticket_update",
                               summary[:500], user_id=str(user.id),
                               guild_id=str(guild.id) if guild else None)
    except Exception:
        pass

def emb(title: str, desc: str) -> discord.Embed:
    from cogs.ui import panel
    return panel(title, desc, EMBED_COLOR)


def staff_only(interaction: discord.Interaction) -> bool:
    return is_staff(interaction.user)  # type: ignore[arg-type]


def _open_ticket_row(guild_id: int, user_id: int):
    with db._conn() as conn:
        return conn.execute(
            "SELECT channel_id FROM tickets WHERE guild_id=? AND owner_id=? "
            "AND status IN ('open','claimed') ORDER BY id DESC LIMIT 1",
            (guild_id, user_id)).fetchone()


class TicketPanelView(discord.ui.View):
    """Ticket Tool-style panel button: 'Create Ticket'.

    Kept with its stable custom_id so the REST-posted panel keeps
    working. The combined panel below adds the type select menu.
    """
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Ticket", style=discord.ButtonStyle.primary, emoji=partial("newr_ticket"), custom_id="newr_support_ticket_panel")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        existing = _open_ticket_row(interaction.guild.id, interaction.user.id)
        if existing:
            from cogs.ui import warn as _warn
            await interaction.response.send_message(embed=_warn("Ticket Already Open", f"You already have an open ticket: <#{existing['channel_id']}>. Please use that one instead of opening another."), ephemeral=True); return
        try:
            channel = await create_ticket_channel(interaction, "Opened from the ticket panel")
        except TicketBannedError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
        except (discord.Forbidden, discord.HTTPException) as e:
            await interaction.response.send_message(f"Could not create a ticket channel: {e}. Please ask staff for help.", ephemeral=True)
            return
        from cogs.ui import ok as _ok
        await interaction.response.send_message(embed=_ok("Ticket Created", f"Your ticket is ready: {channel.mention} — staff have been pinged."), ephemeral=True)


class TicketReasonModal(discord.ui.Modal):
    def __init__(self, ticket_type: str) -> None:
        super().__init__(title=f"{ticket_type} Ticket")
        self.ticket_type = ticket_type
        self.reason_input = discord.ui.TextInput(
            label="Describe your issue", style=discord.TextStyle.paragraph,
            max_length=1000)
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        existing = _open_ticket_row(interaction.guild.id, interaction.user.id)
        if existing:
            from cogs.ui import warn as _warn
            await interaction.response.send_message(embed=_warn("Ticket Already Open", f"You already have an open ticket: <#{existing['channel_id']}>. Please use that one instead of opening another."), ephemeral=True); return
        try:
            channel = await create_ticket_channel(
                interaction, f"[{self.ticket_type}] {self.reason_input}")
        except TicketBannedError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
        except TicketBannedError as e:
            await interaction.response.send_message(str(e), ephemeral=True); return
        except (discord.Forbidden, discord.HTTPException) as e:
            await interaction.response.send_message(f"Could not create a ticket channel: {e}. Please ask staff for help.", ephemeral=True); return
        from cogs.ui import ok as _ok
        await interaction.response.send_message(embed=_ok("Ticket Created", f"Your ticket is ready: {channel.mention} — staff have been pinged."), ephemeral=True)


class TicketTypeView(discord.ui.View):
    """Ticket Tool-style type select: pick a category, then describe.

    The select's stable custom_id is what the REST-posted panel uses;
    the combined view below registers both the select and the button.
    """
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.select(placeholder="Choose a ticket type", custom_id="newr_ticket_type_select",
                       options=[
                           discord.SelectOption(label="General Support", value="General Support",
                                                description="General help or questions", emoji=partial("newr_ticket")),
                           discord.SelectOption(label="Report a Member", value="Report a Member",
                                                description="Report another member to staff", emoji=partial("newr_warn")),
                           discord.SelectOption(label="Bug Report", value="Bug Report",
                                                description="Something is broken", emoji=partial("newr_bug")),
                           discord.SelectOption(label="Appeal", value="Appeal",
                                                description="Appeal a punishment", emoji=partial("newr_scale")),
                           discord.SelectOption(label="Other", value="Other",
                                                description="Anything else", emoji=partial("newr_chat")),
                       ])
    async def choose_type(self, interaction: discord.Interaction, select: discord.ui.Select):  # noqa: ARG002
        await interaction.response.send_modal(TicketReasonModal(select.values[0]))


class TicketPanelCombinedView(TicketTypeView):
    """One panel message with both the type select and Create button.

    This is what /ticket_panel posts and what the REST panel in
    #ticket mirrors (select row + button row, same custom_ids).
    """
    def __init__(self) -> None:
        super().__init__()
        btn = discord.ui.Button(label="Create Ticket", style=discord.ButtonStyle.primary,
                                emoji=partial("newr_ticket"), custom_id="newr_support_ticket_panel")
        async def _open(interaction: discord.Interaction) -> None:
            existing = _open_ticket_row(interaction.guild.id, interaction.user.id)
            if existing:
                await interaction.response.send_message(
                    f"You already have an open ticket: <#{existing['channel_id']}>. "
                    f"Please use that one instead of opening another.", ephemeral=True); return
            try:
                channel = await create_ticket_channel(interaction, "Opened from the ticket panel")
            except (discord.Forbidden, discord.HTTPException) as e:
                await interaction.response.send_message(f"Could not create a ticket channel: {e}. Please ask staff for help.", ephemeral=True); return
            from cogs.ui import ok as _ok
            await interaction.response.send_message(embed=_ok("Ticket Created", f"Your ticket is ready: {channel.mention} — staff have been pinged."), ephemeral=True)
        btn.callback = _open
        self.add_item(btn)


class TicketCloseView(discord.ui.View):
    """Ticket Tool-style buttons inside every ticket channel."""
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.select(placeholder="Set ticket priority", custom_id="newr_ticket_priority",
                       options=[
                           discord.SelectOption(label="Low", value="Low", emoji=partial("newr_low")),
                           discord.SelectOption(label="Medium", value="Medium", emoji=partial("newr_mid")),
                           discord.SelectOption(label="High", value="High", emoji=partial("newr_high")),
                           discord.SelectOption(label="Urgent", value="Urgent", emoji=partial("newr_urgent")),
                       ])
    async def set_priority(self, interaction: discord.Interaction, select: discord.ui.Select):  # noqa: ARG002
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Use this in a ticket channel.", ephemeral=True); return
        with db._conn() as conn:
            conn.execute("UPDATE tickets SET priority=? WHERE channel_id=?",
                         (select.values[0], interaction.channel.id))
        await interaction.response.send_message(
            f"Priority set to **{select.values[0]}** by {interaction.user.mention}")

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji=partial("newr_lock"), custom_id="newr_ticket_close_button")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        row = None
        if isinstance(interaction.channel, discord.TextChannel):
            with db._conn() as conn:
                row = conn.execute("SELECT * FROM tickets WHERE channel_id=?",
                                   (interaction.channel.id,)).fetchone()
        if row is None:
            await interaction.response.send_message("This is not a ticket channel.", ephemeral=True); return
        if interaction.user.id != row["owner_id"] and not staff_only(interaction):
            await interaction.response.send_message("Only the ticket owner or staff can close it.", ephemeral=True); return
        # Ticket Tool close request: record it, announce it in the
        # channel (so it can be cancelled there), and let the
        # hourly loop auto-close it after 24h if nobody acts.
        with db._conn() as conn:
            conn.execute(
                "INSERT INTO ticket_close_requests VALUES (?, ?, ?, ?) "
                "ON CONFLICT(channel_id) DO UPDATE SET requested_by=excluded.requested_by, requested_at=excluded.requested_at",
                (interaction.channel.id, interaction.guild_id, interaction.user.id, db.now()))
        try:
            await interaction.channel.send(
                f"⏳ Close requested by {interaction.user.mention}. This ticket will auto-close in 24 hours "
                f"if nobody cancels the request.",
                view=TicketCloseRequestView())
        except discord.HTTPException:
            pass
        await interaction.response.send_message(
            "Are you sure you want to close this ticket? A transcript will be saved to #logs.",
            view=TicketCloseConfirmView(), ephemeral=True)

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.secondary, emoji=partial("newr_hand"), custom_id="newr_ticket_claim_button")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Use this in a ticket channel.", ephemeral=True); return
        with db._conn() as conn:
            conn.execute("UPDATE tickets SET claimed_by=?, status='claimed' WHERE channel_id=?",
                         (interaction.user.id, interaction.channel.id))
        await interaction.response.send_message(f"{interaction.user.mention} claimed this ticket.")


class TicketCloseRequestView(discord.ui.View):
    """Cancel button for a pending close request (in-channel)."""
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Cancel Close Request", style=discord.ButtonStyle.secondary, custom_id="newr_ticket_close_request_cancel")
    async def cancel_request(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Not a ticket channel.", ephemeral=True); return
        with db._conn() as conn:
            conn.execute("DELETE FROM ticket_close_requests WHERE channel_id=?", (interaction.channel.id,))
        await interaction.response.send_message(
            f"Close request cancelled by {interaction.user.mention}. The ticket stays open.")


class TicketCloseConfirmView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Confirm Close", style=discord.ButtonStyle.danger, custom_id="newr_ticket_close_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Not a ticket channel.", ephemeral=True); return
        await interaction.response.send_message("Closing ticket…", ephemeral=True)
        await close_ticket_channel(interaction.channel, interaction.guild, "Closed via ticket button",
                                   closed_by=interaction.user)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="newr_ticket_close_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        if isinstance(interaction.channel, discord.TextChannel):
            with db._conn() as conn:
                conn.execute("DELETE FROM ticket_close_requests WHERE channel_id=?", (interaction.channel.id,))
        await interaction.response.send_message("Close cancelled.", ephemeral=True)


async def close_ticket_channel(channel: discord.TextChannel, guild: discord.Guild,
                               reason: str, closed_by=None) -> None:
    """Ticket Tool-style close: transcript to #logs + DM to owner, then delete.

    Used by both /ticket_close and the in-ticket Close button, so the
    two paths can never drift apart.
    """
    with db._conn() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE channel_id=?",
                           (channel.id,)).fetchone()
    lines = []
    html_rows = []
    try:
        import html as _html
        async for msg in channel.history(limit=500, oldest_first=True):
            lines.append(f"[{msg.created_at.isoformat()}] {msg.author}: {msg.content}")
            html_rows.append(
                f"<p><b>{_html.escape(str(msg.author))}</b> "
                f"<span style='color:#888'>{msg.created_at.isoformat()}</span><br>"
                f"{_html.escape(msg.content)}</p>")
    except discord.HTTPException:
        pass
    data = ("\n".join(lines) or "(no messages)").encode()
    html_data = ("<html><head><meta charset='utf-8'>"
                 f"<title>Transcript #{channel.name}</title></head><body>"
                 f"<h1>Ticket #{channel.name}</h1>"
                 + "".join(html_rows) + "</body></html>").encode()
    log_ch = None
    log_id = db.get_setting(guild.id, "log_channel", "0") or os.environ.get("LOG_CHANNEL_ID", "0")
    if log_id and log_id != "0":
        ch = guild.get_channel(int(log_id))
        if isinstance(ch, discord.TextChannel):
            log_ch = ch
    if log_ch is not None:
        try:
            await log_ch.send(
                f"📄 Ticket transcript: #{channel.name} (owner <@{row['owner_id']}>) "
                f"closed by {closed_by.mention if closed_by else 'staff'} — {reason}",
                file=discord.File(io.BytesIO(html_data), filename=f"transcript-{channel.name}.html"))
        except discord.HTTPException:
            pass
    if row is not None:
        owner = guild.get_member(row["owner_id"])
        if owner is not None:
            try:
                # Ticket Tool sends the transcript to the user on close;
                # send both the .txt (readable in Discord) and the .html
                # (Ticket Tool's format, same content) so the user gets
                # exactly what staff see in #logs.
                await owner.send(
                    f"Your ticket #{channel.name} in NEWR LABS was closed ({reason}). Transcript attached.",
                    files=[discord.File(io.BytesIO(data), filename=f"transcript-{channel.name}.txt"),
                           discord.File(io.BytesIO(html_data), filename=f"transcript-{channel.name}.html")])
            except discord.HTTPException:
                pass
    with db._conn() as conn:
        conn.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", (channel.id,))
        conn.execute("DELETE FROM ticket_close_requests WHERE channel_id=?", (channel.id,))
    db.set_setting(guild.id, f"ticket_{channel.id}", "closed")
    try:
        await channel.delete(reason=f"Ticket closed: {reason}")
    except discord.HTTPException:
        pass


async def create_ticket_channel(interaction: discord.Interaction, reason: str):
    guild = interaction.guild
    user = interaction.user
    # Sayrix ticket ban: banned users cannot open any ticket type.
    # Existing tickets and invitations are unaffected (only new
    # creations are blocked).
    ban = _ticket_ban_active(guild.id, user.id)
    if ban is not None:
        until = "permanently" if not ban["expires_at"] else f"until {ban['expires_at']}"
        raise TicketBannedError(f"You are ticket-banned {until}. Reason: {ban['reason'] or '-' }")
    return await _create_ticket_channel_body(interaction, reason)


class TicketBannedError(Exception):
    """Raised by create_ticket_channel for a ticket-banned user.

    A plain exception (not an HTTPException) so callers can show
    the ban message cleanly instead of a Discord API error string.
    """


def _create_ticket_overwrites(guild, user):
    return {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }


async def _create_ticket_channel_body(interaction: discord.Interaction, reason: str):
    guild = interaction.guild
    user = interaction.user
    overwrites = _create_ticket_overwrites(guild, user)
    for role in support_roles(guild):
        overwrites[role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
    # Ticket Tool per-category settings: different ticket types go
    # to different categories. Report a Member -> Mod ticket,
    # Appeal -> Executive ticket, everything else -> Tickets.
    # The reason string is "[Type] details" for panel tickets.
    type_category = {
        "Report a Member": 1471169266152767580,
        "Appeal": 1471170522900336863,
    }
    category = None
    if reason.startswith("["):
        ticket_type = reason[1:].split("]", 1)[0]
        cat_id_for_type = type_category.get(ticket_type)
        if cat_id_for_type:
            ch = guild.get_channel(cat_id_for_type)
            if isinstance(ch, discord.CategoryChannel):
                category = ch
    if category is None:
        cat_id = os.environ.get("SUPPORT_CATEGORY_ID")
        if cat_id:
            try:
                category = guild.get_channel(int(cat_id))  # type: ignore[arg-type]
            except ValueError:
                category = None
    # Discord channel names allow only lowercase letters, numbers, - and _.
    import re as _re
    safe = _re.sub(r"[^a-z0-9_-]", "-", user.name.lower()) or "user"
    name = f"ticket-{safe}"[:90].rstrip("-") or "ticket-user"
    channel = await guild.create_text_channel(name, category=category, overwrites=overwrites,
                                              topic=f"Ticket for {user} | {reason}"[:200])
    db.add_row("tickets", guild_id=guild.id, channel_id=channel.id, owner_id=user.id,
               status="open", reason=reason, claimed_by=None, created_at=db.now())
    _brain_note(interaction, "ticket_opened",
                f"Ticket opened in #{channel.name}: {reason}")
    # Ticket Tool pings first responders on open: Team Lead + Helper
    # (the "support" category), falling back to moderators if none.
    from roles import roles_in_categories
    first = roles_in_categories(guild, "support") or roles_in_categories(guild, "moderator")
    pings = " ".join(r.mention for r in first) if first else "Support staff"
    from cogs.ui import make as _make
    await channel.send(
        content=f"{user.mention} {pings}",
        embed=_make("🎟️ Ticket Opened",
                    "Welcome! Staff have been pinged and will claim this ticket shortly.",
                    fields=[("👤 Opened by", f"{user.mention} (ID {user.id})", True),
                            ("📄 Reason", reason, False),
                            ("🛠️ Staff actions", "Use **Close** to close, **Claim** to take ownership, and the priority menu to set urgency.", False)]),
        view=TicketCloseView())
    return channel


def ticket_channel(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel):
        return None
    with db._conn() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE channel_id=?",
                           (interaction.channel.id,)).fetchone()
    return row


def _parse_duration(text: str):
    """Sayrix-style durations: s/m/h/d/w, combinations like 1d12h.

    Returns seconds, or None for lifetime (empty, 'lifetime',
    'permanent'), or raises ValueError for an invalid string.
    """
    import re as _re
    text = (text or "").strip().lower()
    if text in ("", "lifetime", "permanent", "forever"):
        return None
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    total = 0
    pos = 0
    for num, unit in _re.findall(r"(\d+)\s*([smhdw])", text):
        total += int(num) * units[unit]
        pos += len(num) + len(unit)
    # Allow spaces between parts, e.g. "1d 12h".
    cleaned = _re.sub(r"\s+", "", text)
    matched = "".join(f"{n}{u}" for n, u in _re.findall(r"(\d+)\s*([smhdw])", text))
    if total == 0 or matched != cleaned:
        raise ValueError(f"Invalid duration '{text}'. Use e.g. 7d, 1d12h, 2w, or lifetime.")
    return total


def _ticket_ban_active(guild_id: int, user_id: int):
    """Return the active ticket ban row, or None.

    Expired timed bans are deleted here, so they expire
    automatically even while the bot was offline (Sayrix
    behaviour): the next check simply finds no ban.
    """
    with db._conn() as conn:
        row = conn.execute("SELECT * FROM ticket_bans WHERE guild_id=? AND user_id=?",
                           (guild_id, user_id)).fetchone()
        if row is None:
            return None
        if row["expires_at"]:
            try:
                exp = datetime.fromisoformat(row["expires_at"])
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= exp:
                    conn.execute("DELETE FROM ticket_bans WHERE guild_id=? AND user_id=?",
                                 (guild_id, user_id))
                    return None
            except Exception:
                pass
        return row


class Support(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self._close_request_loop.start()

    async def cog_unload(self) -> None:
        self._close_request_loop.cancel()

    @tasks.loop(minutes=60)
    async def _close_request_loop(self) -> None:
        """Ticket Tool close-request timer: a close request that
        nobody cancels or confirms for 24h auto-closes the ticket.
        Requests live in the DB, so the timer survives restarts."""
        try:
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            with db._conn() as conn:
                rows = conn.execute(
                    "SELECT channel_id, guild_id FROM ticket_close_requests WHERE requested_at<=?",
                    (cutoff,)).fetchall()
            for row in rows:
                guild = self.bot.get_guild(row["guild_id"])
                if guild is None:
                    continue
                channel = guild.get_channel(row["channel_id"])
                if not isinstance(channel, discord.TextChannel):
                    continue
                with db._conn() as conn:
                    ticket = conn.execute("SELECT status FROM tickets WHERE channel_id=?",
                                          (channel.id,)).fetchone()
                if ticket is None or ticket["status"] not in ("open", "claimed"):
                    with db._conn() as conn:
                        conn.execute("DELETE FROM ticket_close_requests WHERE channel_id=?", (channel.id,))
                    continue
                await close_ticket_channel(
                    channel, guild, "Auto-closed: close request unanswered for 24 hours")
        except Exception:
            pass

    @_close_request_loop.before_loop
    async def _before_close_loop(self) -> None:
        # In a real run this waits for login. In dry-run (no login)
        # wait_until_ready raises RuntimeError; swallow it so the
        # dry-run can still count commands, and cancel the loop.
        try:
            await self.bot.wait_until_ready()
        except RuntimeError:
            self._close_request_loop.cancel()

    # ---- tickets ----
    @app_commands.command(name="ticket_create", description="Create a support ticket channel")
    @app_commands.describe(reason="What do you need help with?")
    async def ticket_create(self, interaction: discord.Interaction, reason: str = "General support"):
        await interaction.response.defer(ephemeral=True)
        # Point to an existing open ticket instead of opening duplicates.
        with db._conn() as conn:
            existing = conn.execute(
                "SELECT channel_id FROM tickets WHERE guild_id=? AND owner_id=? AND status IN ('open','claimed') ORDER BY id DESC LIMIT 1",
                (interaction.guild.id, interaction.user.id)).fetchone()
        if existing:
            await interaction.followup.send(
                f"You already have an open ticket: <#{existing['channel_id']}>. Please use that one instead of opening another.", ephemeral=True)
            return
        try:
            channel = await create_ticket_channel(interaction, reason)
        except TicketBannedError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        except (discord.Forbidden, discord.HTTPException) as e:
            await interaction.followup.send(f"Could not create a ticket channel: {e}. Please ask staff for help.", ephemeral=True)
            return
        # Smart triage (local, free): classify + route, posted in the ticket.
        try:
            await channel.send(smart.triage_text(reason))
        except discord.HTTPException:
            pass
        await interaction.followup.send(f"Ticket created: {channel.mention}\n{smart.triage_text(reason)}", ephemeral=True)

    @app_commands.command(name="ticket_panel", description="Post a ticket panel with an open-ticket button")
    async def ticket_panel(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=emb("🎟️ Create a Ticket", "Need help? Pick a ticket type below, tell us what happened in the form, and staff will be pinged.\n\n**1.** Choose a type (General, Report, Bug, Appeal, Other)\n**2.** Fill in the reason\n**3.** Wait in your ticket channel — staff will claim it"),
            view=TicketPanelCombinedView())

    @app_commands.command(name="ticket_close", description="Close the current ticket channel")
    @app_commands.describe(reason="Why is this ticket closing?")
    async def ticket_close(self, interaction: discord.Interaction, reason: str = "Resolved"):
        row = ticket_channel(interaction)
        if not row:
            await interaction.response.send_message("This is not a ticket channel.", ephemeral=True); return
        if interaction.user.id != row["owner_id"] and not staff_only(interaction):
            await interaction.response.send_message("Only the ticket owner or staff can close it.", ephemeral=True); return
        await interaction.response.send_message(
            f"Closing ticket. Reason: {reason}. A transcript will be saved to #logs and DM'd to the owner.")
        await close_ticket_channel(interaction.channel, interaction.guild, reason,  # type: ignore[arg-type]
                                   closed_by=interaction.user)

    @app_commands.command(name="ticket_claim", description="Claim the current ticket as staff")
    async def ticket_claim(self, interaction: discord.Interaction):
        row = ticket_channel(interaction)
        if not row or not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            conn.execute("UPDATE tickets SET claimed_by=?, status='claimed' WHERE channel_id=?",
                         (interaction.user.id, interaction.channel.id))
        await interaction.response.send_message(f"{interaction.user.mention} claimed this ticket.")

    @app_commands.command(name="ticketban", description="Ban a user from opening tickets (Sayrix-style, staff with Ban Members)")
    @app_commands.describe(user="User to ticket-ban", duration="e.g. 7d, 1d12h, 2w, or lifetime (default: lifetime)",
                           reason="Why they are ticket-banned")
    async def ticketban(self, interaction: discord.Interaction, user: discord.Member,
                        duration: str = "lifetime", reason: str = ""):
        # Sayrix gate: Ban Members or Administrator permission.
        # NEWR staff roles are also allowed, so a staff member whose
        # Discord role lacks Ban Members can still use it.
        perms = interaction.user.guild_permissions  # type: ignore[attr-defined]
        if not (perms.ban_members or perms.administrator or staff_only(interaction)):
            await interaction.response.send_message("You need Ban Members permission or a staff role.", ephemeral=True); return
        try:
            seconds = _parse_duration(duration)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True); return
        expires = None
        if seconds is not None:
            expires = (datetime.now(timezone.utc) + __import__("datetime").timedelta(seconds=seconds)).isoformat()
        with db._conn() as conn:
            conn.execute(
                "INSERT INTO ticket_bans VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id, guild_id) DO UPDATE SET expires_at=excluded.expires_at, reason=excluded.reason, banned_by=excluded.banned_by, created_at=excluded.created_at",
                (user.id, interaction.guild_id, expires, reason, interaction.user.id, db.now()))
        until = "permanently" if expires is None else f"until {expires}"
        try:
            from cogs.modlog import log_action
            await log_action(interaction.guild, "Ticket Banned", user, interaction.user,  # type: ignore[arg-type]
                             f"Ticket-banned {until}", extra=f"Reason: {reason or '-'}")
        except Exception:
            pass
        await interaction.response.send_message(
            f"{user.mention} is ticket-banned {until}. Existing tickets are unaffected.", ephemeral=True)

    @app_commands.command(name="ticketunban", description="Lift a ticket ban early (Sayrix-style)")
    @app_commands.describe(user="User to un-ticket-ban")
    async def ticketunban(self, interaction: discord.Interaction, user: discord.Member):
        perms = interaction.user.guild_permissions  # type: ignore[attr-defined]
        if not (perms.ban_members or perms.administrator or staff_only(interaction)):
            await interaction.response.send_message("You need Ban Members permission or a staff role.", ephemeral=True); return
        with db._conn() as conn:
            cur = conn.execute("DELETE FROM ticket_bans WHERE guild_id=? AND user_id=?",
                               (interaction.guild_id, user.id))
            removed = cur.rowcount
        if removed:
            await interaction.response.send_message(f"{user.mention} can open tickets again.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{user.mention} was not ticket-banned.", ephemeral=True)

    @app_commands.command(name="ticket_add", description="Add a member to the current ticket")
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member):
        row = ticket_channel(interaction)
        if not row or not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True)  # type: ignore[union-attr]
        await interaction.response.send_message(f"Added {member.mention} to this ticket.")

    @app_commands.command(name="ticket_remove", description="Remove a member from the current ticket")
    async def ticket_remove(self, interaction: discord.Interaction, member: discord.Member):
        row = ticket_channel(interaction)
        if not row or not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.channel.set_permissions(member, view_channel=False)  # type: ignore[union-attr]
        await interaction.response.send_message(f"Removed {member.mention} from this ticket.")

    @app_commands.command(name="ticket_transcript", description="Send a transcript of the current ticket channel")
    async def ticket_transcript(self, interaction: discord.Interaction):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Use this in a text channel.", ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        lines = []
        async for msg in interaction.channel.history(limit=500, oldest_first=True):
            lines.append(f"[{msg.created_at.isoformat()}] {msg.author}: {msg.content}")
        data = "\n".join(lines) or "(no messages)"
        await interaction.followup.send(file=discord.File(io.BytesIO(data.encode()), filename="transcript.txt"),
                                        ephemeral=True)

    @app_commands.command(name="ticket_list", description="List open tickets")
    async def ticket_list(self, interaction: discord.Interaction):
        rows = db.list_rows("tickets", interaction.guild.id, 20)
        open_rows = [r for r in rows if r["status"] in ("open", "claimed")]
        text = "\n".join(f"#{r['id']} <#{r['channel_id']}> owner <@{r['owner_id']}> ({r['status']}) — {r['reason']}"
                         for r in open_rows) or "No open tickets."
        await interaction.response.send_message(embed=emb("Open Tickets", text), ephemeral=True)

    @app_commands.command(name="ticket_note", description="Add a private staff note to a ticket (staff)")
    async def ticket_note(self, interaction: discord.Interaction, note: str):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        db.add_row("notes", guild_id=interaction.guild.id, user_id=interaction.user.id,
                   author_id=interaction.user.id, note=note, created_at=db.now())
        await interaction.response.send_message("Staff note saved.", ephemeral=True)

    @app_commands.command(name="ticket_escalate", description="Escalate the current ticket to admins")
    async def ticket_escalate(self, interaction: discord.Interaction):
        row = ticket_channel(interaction)
        if not row:
            await interaction.response.send_message("Use this in a ticket channel.", ephemeral=True); return
        if interaction.user.id != row["owner_id"] and not staff_only(interaction):
            await interaction.response.send_message("Only the ticket owner or staff can escalate it.", ephemeral=True); return
        admins = [r.mention for r in interaction.guild.roles if r.permissions.administrator]
        await interaction.response.send_message(" ".join(admins) + " — this ticket has been escalated by "
                                + interaction.user.mention)

    # NOTE: /ticket_unclaim and /support_status were traded for
    # /ticketban + /ticketunban (Discord guild cap is 100).
    # Unclaim is still possible in practice: another staff member
    # claiming the ticket overwrites claimed_by. Open-ticket count
    # is still available via /ticket_list.

    # ---- FAQ / helpdesk ----
    @app_commands.command(name="faq", description="Look up a FAQ topic (smart fuzzy match)")
    async def faq(self, interaction: discord.Interaction, topic: str):
        with db._conn() as conn:
            row = conn.execute("SELECT * FROM faqs WHERE guild_id IN (0, ?) AND topic=?",
                               (interaction.guild.id, topic.lower())).fetchone()
            if row:
                await interaction.response.send_message(embed=emb(f"FAQ: {topic}", row["answer"]), ephemeral=True); return
            # Smart fuzzy match: no exact topic? Suggest the closest answer.
            rows = conn.execute("SELECT topic, answer FROM faqs WHERE guild_id IN (0, ?)",
                                (interaction.guild.id,)).fetchall()
        faqs = [{"topic": r["topic"], "answer": r["answer"]} for r in rows]
        best, score, related = smart.fuzzy_faq(topic, faqs)
        if best and score >= 0.30:
            rel = ", ".join(r["topic"] for r in related) or "none"
            await interaction.response.send_message(
                embed=emb(f"FAQ (closest match: {best['topic']}, {score:.0%} match)",
                          f"{best['answer']}\n\nRelated topics: {rel}\n\n💡 Tip of the day ({smart.daily_tip()['category']}): {smart.daily_tip()['text']}"),
                ephemeral=True); return
        tip = smart.daily_tip()
        await interaction.response.send_message(
            f"No close FAQ for '{topic}'. Try /faq_list.\n\n💡 Tip of the day ({tip['category']}): {tip['text']}",
            ephemeral=True)

    @app_commands.command(name="faq_add", description="Add a FAQ entry (staff)")
    async def faq_add(self, interaction: discord.Interaction, topic: str, answer: str):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            conn.execute("INSERT INTO faqs VALUES (?, ?, ?) ON CONFLICT(guild_id, topic) DO UPDATE SET answer=excluded.answer",
                         (interaction.guild.id, topic.lower(), answer))
        await interaction.response.send_message(f"FAQ '{topic}' saved.")

    @app_commands.command(name="faq_list", description="List FAQ topics")
    async def faq_list(self, interaction: discord.Interaction):
        with db._conn() as conn:
            rows = conn.execute("SELECT topic FROM faqs WHERE guild_id IN (0, ?) ORDER BY topic",
                                (interaction.guild.id,)).fetchall()
        text = ", ".join(r["topic"] for r in rows) or "No FAQs yet."
        await interaction.response.send_message(embed=emb("FAQ Topics", text), ephemeral=True)

    @app_commands.command(name="faq_remove", description="Remove a FAQ entry (staff)")
    async def faq_remove(self, interaction: discord.Interaction, topic: str):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            conn.execute("DELETE FROM faqs WHERE guild_id=? AND topic=?", (interaction.guild.id, topic.lower()))
        await interaction.response.send_message(f"FAQ '{topic}' removed.")

    @app_commands.command(name="helpdesk", description="Show how to get help on this server (with today's smart tip)")
    async def helpdesk(self, interaction: discord.Interaction):
        tip = smart.daily_tip()
        await interaction.response.send_message(embed=emb(
            "Helpdesk", "1. Use /ticket_create for private help.\n2. Use /faq for common questions (it fuzzy-matches, so exact wording is not needed).\n"
            "3. Use /report to report a problem user.\n4. Use /staff_ping only for urgent issues.\n\n"
            f"💡 Tip of the day ({tip['category']}): {tip['text']}"),
            ephemeral=True)

    @app_commands.command(name="staff_ping", description="Ping support staff for an urgent issue")
    async def staff_ping(self, interaction: discord.Interaction, issue: str):
        mentions = " ".join(r.mention for r in support_roles(interaction.guild)) or "staff"
        await interaction.response.send_message(f"{mentions} Urgent help requested by {interaction.user.mention}: {issue}\n{smart.triage_text(issue)}")

    # ---- reports / suggestions / bugs / appeals / feedback ----
    @app_commands.command(name="report", description="Report a member to staff")
    @app_commands.choices(category=[
        app_commands.Choice(name="Low", value="Low"),
        app_commands.Choice(name="Medium", value="Medium"),
        app_commands.Choice(name="Severe", value="Severe")])
    @app_commands.describe(member="Who is being reported", reason="Report reason",
                           category="Low: minor violation, Medium: disruptive, Severe: serious/urgent",
                           evidence="Screenshot/evidence (optional)")
    async def report(self, interaction: discord.Interaction, member: discord.Member, reason: str,
                     category: app_commands.Choice[str] = None,
                     evidence: discord.Attachment = None):
        cat = category.value if category is not None else "Medium"
        # Anti-spam: satu pelapor tidak bisa report target yang sama
        # berkali-kali dalam 10 menit (report terbuka yang sama).
        with db._conn() as conn:
            dup = conn.execute(
                "SELECT COUNT(*) FROM reports WHERE guild_id=? AND reporter_id=? AND target_id=? "
                "AND created_at > datetime('now', '-10 minutes')",
                (interaction.guild.id, interaction.user.id, member.id)).fetchone()[0]
        if dup:
            await interaction.response.send_message(
                "You already reported this user in the last 10 minutes. "
                "Please wait for staff to review the previous report first.", ephemeral=True)
            return
        rid = db.add_row("reports", guild_id=interaction.guild.id, reporter_id=interaction.user.id,
                         target_id=member.id, reason=reason, created_at=db.now(),
                         category=cat, status="open")
        _brain_note(interaction, "report_filed",
                    f"Report #{rid} ({cat}) against user {member.id}: {reason}")
        from cogs.reportflow import post_report_embed
        msg = await post_report_embed(interaction.guild, rid, member.id, interaction.user.id,
                                      cat, reason, evidence.url if evidence else None)
        # Severe = urgent: ping staff in the report channel too.
        if cat == "Severe" and msg is not None:
            try:
                mentions = " ".join(r.mention for r in support_roles(interaction.guild)) or "staff"
                await msg.reply(f"{mentions} New SEVERE report, please review immediately.")
            except Exception:
                pass
        await interaction.response.send_message(
            f"Report #{rid} ({cat}) against {member.mention} has been sent to staff. "
            "Staff will review it via the buttons in the report channel.\n"
            "⚠️ Do not report people arbitrarily: if your report is proven false, "
            "you yourself can be warned/muted.\n"
            f"{smart.triage_text(reason)}", ephemeral=True)

    @app_commands.command(name="report_list", description="List open reports as follow-up cards (staff)")
    async def report_list(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        # Shared list when run in a staff-only channel (#reports / #logs):
        # everyone in that channel can see it and help, instead of only the
        # person who ran the command. Anywhere else it stays ephemeral, so
        # report details (reporter, reason) do not leak into a public channel.
        report_ch = db.get_setting(interaction.guild.id, "report_channel", "0")
        log_ch = db.get_setting(interaction.guild.id, "log_channel", "0")
        shared = str(interaction.channel_id) in (str(report_ch), str(log_ch))
        await interaction.response.defer(ephemeral=not shared)
        # Only OPEN reports: closed / innocent / false ones are history,
        # not work to follow up. Old reports without a category show "Lama".
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM reports WHERE guild_id=? AND (status IS NULL OR status='open') "
                "ORDER BY id DESC LIMIT 10", (interaction.guild.id,)).fetchall()
        if not rows:
            await interaction.followup.send(
                "🎉 No open reports. All reports have been handled / closed.",
                ephemeral=not shared)
            return
        await interaction.followup.send(
            f"📋 **{len(rows)} open report(s)** — tap the button on each card to "
            "jump to the original report message in the report channel, then use the "
            "Warn / Mute / Ban / Not Guilty buttons there."
            + ("" if shared else " (Only you can see this list here — run /report_list in #reports to share it with other staff.)"),
            ephemeral=not shared)
        from cogs.reportflow import ReportView, count_warns
        from datetime import timezone as _tz
        from zoneinfo import ZoneInfo as _ZI
        for r in rows:
            raw_cat = r["category"] if "category" in r.keys() and r["category"] else None
            cat = {"Ringan": "Low", "Sedang": "Medium", "Parah": "Severe"}.get(raw_cat, raw_cat or "Legacy")
            colour = 0xED4245 if cat == "Severe" else 0xFEE75C if cat == "Medium" else 0x57F287
            date_str = r["created_at"] or "-"
            try:
                dt = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_tz.utc)
                dt = dt.astimezone(_ZI("Asia/Jakarta"))
                days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                months = ["", "January", "February", "March", "April", "May", "June",
                          "July", "August", "September", "October", "November", "December"]
                date_str = f"{days[dt.weekday()]}, {dt.day} {months[dt.month]} {dt.year} {dt.strftime('%H:%M')} WIB"
            except Exception:
                pass
            embed = discord.Embed(
                title=f"Report #{r['id']} — {cat}",
                description=(f"**Target:** <@{r['target_id']}> (ID {r['target_id']})\n"
                             f"**Reporter:** <@{r['reporter_id']}> (ID {r['reporter_id']})\n"
                             f"**Reason:** {r['reason']}\n"
                             f"**Date:** {date_str}\n"
                             f"**Target's previous warns:** {count_warns(interaction.guild.id, r['target_id'])}"),
                colour=colour, timestamp=datetime.now(timezone.utc))
            member = interaction.guild.get_member(r["target_id"])
            if member is not None:
                try:
                    embed.set_thumbnail(url=member.display_avatar.url)
                except Exception:
                    pass
            # Kartu dengan pesan asli -> tombol link loncat ke sana
            # (tombol aksi tetap di pesan asli, biar tidak ada dua versi
            # tombol yang bisa dobel-aksi). Report lama tanpa pesan asli
            # -> tombol aksi langsung di kartu ini.
            msg_id = r["message_id"] if "message_id" in r.keys() else None
            ch_id = r["channel_id"] if "channel_id" in r.keys() else None
            if msg_id and ch_id:
                view = discord.ui.View(timeout=None)
                view.add_item(discord.ui.Button(
                    label="Open Original Report →", style=discord.ButtonStyle.link,
                    url=f"https://discord.com/channels/{interaction.guild.id}/{ch_id}/{msg_id}"))
                await interaction.followup.send(embed=embed, view=view, ephemeral=not shared)
            else:
                await interaction.followup.send(
                    embed=embed,
                    view=ReportView(r["id"], r["target_id"], r["reporter_id"],
                                    count_warns(interaction.guild.id, r["target_id"]) + 1),
                    ephemeral=not shared)

    @app_commands.command(name="suggest", description="Submit a suggestion for the server")
    async def suggest(self, interaction: discord.Interaction, suggestion: str):
        sid = db.add_row("suggestions", guild_id=interaction.guild.id, author_id=interaction.user.id,
                         text=suggestion, created_at=db.now())
        await interaction.response.send_message(f"Suggestion #{sid} recorded. Thanks!\n{smart.triage_text(suggestion)}", ephemeral=True)

    @app_commands.command(name="suggestion_list", description="List recent suggestions")
    async def suggestion_list(self, interaction: discord.Interaction):
        rows = db.list_rows("suggestions", interaction.guild.id, 20)
        text = "\n".join(f"#{r['id']} by <@{r['author_id']}>: {r['text']}" for r in rows) or "No suggestions."
        await interaction.response.send_message(embed=emb("Suggestions", text), ephemeral=True)

    @app_commands.command(name="bug", description="Report a bug in the server or bot")
    async def bug(self, interaction: discord.Interaction, description: str):
        bid = db.add_row("bugs", guild_id=interaction.guild.id, author_id=interaction.user.id,
                         text=description, created_at=db.now())
        _brain_note(interaction, "bug_filed",
                    f"Bug #{bid}: {description}")
        await interaction.response.send_message(f"Bug #{bid} recorded. Thanks for reporting it.\n{smart.triage_text(description)}", ephemeral=True)

    @app_commands.command(name="bug_list", description="List recent bug reports (staff)")
    async def bug_list(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        rows = db.list_rows("bugs", interaction.guild.id, 20)
        text = "\n".join(f"#{r['id']} by <@{r['author_id']}>: {r['text']}" for r in rows) or "No bugs."
        await interaction.response.send_message(embed=emb("Bugs", text), ephemeral=True)

    @app_commands.command(name="appeal", description="Appeal a moderation action")
    async def appeal(self, interaction: discord.Interaction, explanation: str):
        aid = db.add_row("appeals", guild_id=interaction.guild.id, author_id=interaction.user.id,
                         text=explanation, created_at=db.now(),
                         kind="general", ref_id=0, status="open",
                         target_id=interaction.user.id)
        _brain_note(interaction, "appeal_filed",
                    f"Appeal #{aid}: {explanation}")
        # Same review flow as DM appeals: post to #appeals with
        # Terima/Tolak buttons, so staff do not have to hunt /appeal_list.
        try:
            from cogs.reportflow import AppealReviewView, resolve_appeal_channel
            channel = await resolve_appeal_channel(interaction.guild)
            if channel is not None:
                embed = discord.Embed(
                    title=f"📝 Appeal #{aid} — general",
                    description=(f"**User:** {interaction.user.mention} (ID {interaction.user.id})\n"
                                 f"**Explanation:** {explanation}"),
                    colour=0x5865F2)
                msg = await channel.send(embed=embed,
                                   view=AppealReviewView(aid, interaction.user.id, "general"))
                with db._conn() as conn:
                    conn.execute("UPDATE appeals SET message_id=?, channel_id=? WHERE id=?",
                                 (msg.id, channel.id, aid))
        except Exception:
            pass
        await interaction.response.send_message(f"Appeal #{aid} filed. Staff will review it.\n{smart.triage_text(explanation)}", ephemeral=True)

    @app_commands.command(name="appeal_list", description="List open appeals as cards staff can see and decide (staff)")
    async def appeal_list(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        # Same sharing rule as /report_list: public in #appeals / #logs
        # (staff-only channels), ephemeral anywhere else so appeal
        # details do not leak into a public channel.
        appeal_ch = db.get_setting(interaction.guild.id, "appeal_channel", "0")
        log_ch = db.get_setting(interaction.guild.id, "log_channel", "0")
        shared = str(interaction.channel_id) in (str(appeal_ch), str(log_ch))
        await interaction.response.defer(ephemeral=not shared)
        with db._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM appeals WHERE guild_id=? AND (status IS NULL OR status='open') "
                "ORDER BY id DESC LIMIT 10", (interaction.guild.id,)).fetchall()
        if not rows:
            await interaction.followup.send(
                "🎉 No open appeals. All appeals have been decided / closed.",
                ephemeral=not shared)
            return
        await interaction.followup.send(
            f"📋 **{len(rows)} open appeal(s)** — tap the button on each card to "
            "jump to the original appeal message in #appeals, then use the "
            "Accept / Reject buttons there."
            + ("" if shared else " (Only you can see this list here — run /appeal_list in #appeals to share it with other staff.)"),
            ephemeral=not shared)
        from cogs.reportflow import AppealReviewView
        from datetime import timezone as _tz
        from zoneinfo import ZoneInfo as _ZI
        for r in rows:
            kind = r["kind"] if "kind" in r.keys() and r["kind"] else "general"
            target_id = r["target_id"] if "target_id" in r.keys() and r["target_id"] else r["author_id"]
            date_str = r["created_at"] or "-"
            try:
                dt = datetime.fromisoformat(str(r["created_at"]).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_tz.utc)
                dt = dt.astimezone(_ZI("Asia/Jakarta"))
                days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                months = ["", "January", "February", "March", "April", "May", "June",
                          "July", "August", "September", "October", "November", "December"]
                date_str = f"{days[dt.weekday()]}, {dt.day} {months[dt.month]} {dt.year} {dt.strftime('%H:%M')} WIB"
            except Exception:
                pass
            embed = discord.Embed(
                title=f"Appeal #{r['id']} — {kind}",
                description=(f"**User:** <@{target_id}> (ID {target_id})\n"
                             f"**Filed by:** <@{r['author_id']}> (ID {r['author_id']})\n"
                             f"**Explanation:** {(r['text'] or '')[:1000]}\n"
                             f"**Date:** {date_str}"),
                colour=0x5865F2, timestamp=datetime.now(timezone.utc))
            msg_id = r["message_id"] if "message_id" in r.keys() else None
            ch_id = r["channel_id"] if "channel_id" in r.keys() else None
            if msg_id and ch_id:
                view = discord.ui.View(timeout=None)
                view.add_item(discord.ui.Button(
                    label="Open Original Appeal →", style=discord.ButtonStyle.link,
                    url=f"https://discord.com/channels/{interaction.guild.id}/{ch_id}/{msg_id}"))
                await interaction.followup.send(embed=embed, view=view, ephemeral=not shared)
            else:
                await interaction.followup.send(
                    embed=embed,
                    view=AppealReviewView(r["id"], target_id, kind),
                    ephemeral=not shared)

    @app_commands.command(name="feedback", description="Leave feedback about support")
    @app_commands.choices(rating=[app_commands.Choice(name=str(i), value=i) for i in range(1, 6)])
    async def feedback(self, interaction: discord.Interaction, rating: app_commands.Choice[int], comment: str = ""):
        db.add_row("feedback", guild_id=interaction.guild.id, author_id=interaction.user.id,
                   rating=rating.value, comment=comment, created_at=db.now())
        await interaction.response.send_message(f"Thanks for the {rating.value}/5 feedback!", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Support(bot))
