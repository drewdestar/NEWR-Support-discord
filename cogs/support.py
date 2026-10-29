"""Support cog: tickets, FAQ, reports, suggestions, bugs, appeals, feedback."""
from __future__ import annotations

import io
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

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
    return discord.Embed(title=title, description=desc, color=EMBED_COLOR,
                         timestamp=datetime.now(timezone.utc))


def staff_only(interaction: discord.Interaction) -> bool:
    return is_staff(interaction.user)  # type: ignore[arg-type]


class TicketPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Open a Support Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="newr_support_ticket_panel")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        try:
            channel = await create_ticket_channel(interaction, "Opened from the ticket panel")
        except (discord.Forbidden, discord.HTTPException) as e:
            await interaction.response.send_message(f"Could not create a ticket channel: {e}. Please ask staff for help.", ephemeral=True)
            return
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)


async def create_ticket_channel(interaction: discord.Interaction, reason: str):
    guild = interaction.guild
    user = interaction.user
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    for role in support_roles(guild):
        overwrites[role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
    category = None
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
    await channel.send(f"{user.mention} Welcome! Support staff have been pinged. Reason: {reason}")
    return channel


def ticket_channel(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel):
        return None
    with db._conn() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE channel_id=?",
                           (interaction.channel.id,)).fetchone()
    return row


class Support(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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
        await interaction.response.send_message(embed=emb("Support Tickets", "Click below to open a ticket."),
                                                view=TicketPanelView())

    @app_commands.command(name="ticket_close", description="Close the current ticket channel")
    @app_commands.describe(reason="Why is this ticket closing?")
    async def ticket_close(self, interaction: discord.Interaction, reason: str = "Resolved"):
        row = ticket_channel(interaction)
        if not row:
            await interaction.response.send_message("This is not a ticket channel.", ephemeral=True); return
        if interaction.user.id != row["owner_id"] and not staff_only(interaction):
            await interaction.response.send_message("Only the ticket owner or staff can close it.", ephemeral=True); return
        db.set_setting(interaction.guild.id, f"ticket_{row['channel_id']}", "closed")  # status marker
        with db._conn() as conn:
            conn.execute("UPDATE tickets SET status='closed' WHERE channel_id=?",
                         (interaction.channel.id,))
        await interaction.response.send_message(f"Closing ticket. Reason: {reason}. Channel will be deleted in a moment.")
        try:
            await interaction.channel.delete(reason=f"Ticket closed: {reason}")  # type: ignore[union-attr]
        except discord.HTTPException:
            pass

    @app_commands.command(name="ticket_claim", description="Claim the current ticket as staff")
    async def ticket_claim(self, interaction: discord.Interaction):
        row = ticket_channel(interaction)
        if not row or not staff_only(interaction):
            await interaction.response.send_message("Staff only, in a ticket channel.", ephemeral=True); return
        with db._conn() as conn:
            conn.execute("UPDATE tickets SET claimed_by=?, status='claimed' WHERE channel_id=?",
                         (interaction.user.id, interaction.channel.id))
        await interaction.response.send_message(f"{interaction.user.mention} claimed this ticket.")

    @app_commands.command(name="ticket_unclaim", description="Release a claimed ticket")
    async def ticket_unclaim(self, interaction: discord.Interaction):
        row = ticket_channel(interaction)
        if not row or not staff_only(interaction):
            await interaction.response.send_message("Staff only, in a ticket channel.", ephemeral=True); return
        with db._conn() as conn:
            conn.execute("UPDATE tickets SET claimed_by=NULL, status='open' WHERE channel_id=?",
                         (interaction.channel.id,))
        await interaction.response.send_message("Ticket released back to the queue.")

    @app_commands.command(name="ticket_add", description="Add a member to the current ticket")
    async def ticket_add(self, interaction: discord.Interaction, member: discord.Member):
        row = ticket_channel(interaction)
        if not row or not staff_only(interaction):
            await interaction.response.send_message("Staff only, in a ticket channel.", ephemeral=True); return
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True)  # type: ignore[union-attr]
        await interaction.response.send_message(f"Added {member.mention} to this ticket.")

    @app_commands.command(name="ticket_remove", description="Remove a member from the current ticket")
    async def ticket_remove(self, interaction: discord.Interaction, member: discord.Member):
        row = ticket_channel(interaction)
        if not row or not staff_only(interaction):
            await interaction.response.send_message("Staff only, in a ticket channel.", ephemeral=True); return
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
            await interaction.response.send_message("Staff only.", ephemeral=True); return
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

    @app_commands.command(name="support_status", description="Show open ticket count and staff on the server")
    async def support_status(self, interaction: discord.Interaction):
        rows = db.list_rows("tickets", interaction.guild.id, 100)
        open_n = sum(1 for r in rows if r["status"] in ("open", "claimed"))
        staff = [m for m in interaction.guild.members if is_staff(m)]
        await interaction.response.send_message(embed=emb("Support Status", f"Open tickets: {open_n}\nStaff members: {len(staff)}"),
                                                ephemeral=True)

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
            await interaction.response.send_message("Staff only.", ephemeral=True); return
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
            await interaction.response.send_message("Staff only.", ephemeral=True); return
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
    async def report(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        rid = db.add_row("reports", guild_id=interaction.guild.id, reporter_id=interaction.user.id,
                         target_id=member.id, reason=reason, created_at=db.now())
        _brain_note(interaction, "report_filed",
                    f"Report #{rid} against user {member.id}: {reason}")
        await interaction.response.send_message(f"Report #{rid} filed against {member.mention}. Staff will review it.\n{smart.triage_text(reason)}", ephemeral=True)

    @app_commands.command(name="report_list", description="List recent reports (staff)")
    async def report_list(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        rows = db.list_rows("reports", interaction.guild.id, 20)
        text = "\n".join(f"#{r['id']} target <@{r['target_id']}> by <@{r['reporter_id']}>: {r['reason']}" for r in rows) or "No reports."
        await interaction.response.send_message(embed=emb("Reports", text), ephemeral=True)

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
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        rows = db.list_rows("bugs", interaction.guild.id, 20)
        text = "\n".join(f"#{r['id']} by <@{r['author_id']}>: {r['text']}" for r in rows) or "No bugs."
        await interaction.response.send_message(embed=emb("Bugs", text), ephemeral=True)

    @app_commands.command(name="appeal", description="Appeal a moderation action")
    async def appeal(self, interaction: discord.Interaction, explanation: str):
        aid = db.add_row("appeals", guild_id=interaction.guild.id, author_id=interaction.user.id,
                         text=explanation, created_at=db.now())
        _brain_note(interaction, "appeal_filed",
                    f"Appeal #{aid}: {explanation}")
        await interaction.response.send_message(f"Appeal #{aid} filed. Staff will review it.\n{smart.triage_text(explanation)}", ephemeral=True)

    @app_commands.command(name="appeal_list", description="List appeals (staff)")
    async def appeal_list(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True); return
        rows = db.list_rows("appeals", interaction.guild.id, 20)
        text = "\n".join(f"#{r['id']} by <@{r['author_id']}>: {r['text']}" for r in rows) or "No appeals."
        await interaction.response.send_message(embed=emb("Appeals", text), ephemeral=True)

    @app_commands.command(name="feedback", description="Leave feedback about support")
    @app_commands.choices(rating=[app_commands.Choice(name=str(i), value=i) for i in range(1, 6)])
    async def feedback(self, interaction: discord.Interaction, rating: app_commands.Choice[int], comment: str = ""):
        db.add_row("feedback", guild_id=interaction.guild.id, author_id=interaction.user.id,
                   rating=rating.value, comment=comment, created_at=db.now())
        await interaction.response.send_message(f"Thanks for the {rating.value}/5 feedback!", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Support(bot))
