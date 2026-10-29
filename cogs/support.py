"""Support cog: tickets, FAQ, reports, suggestions, bugs, appeals, feedback."""
from __future__ import annotations

import io
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import db
from roles import is_staff, support_roles

EMBED_COLOR = 0x5865F2


def emb(title: str, desc: str) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=EMBED_COLOR,
                         timestamp=datetime.now(timezone.utc))


def staff_only(interaction: discord.Interaction) -> bool:
    return is_staff(interaction.user)  # type: ignore[arg-type]


class TicketPanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Open a Support Ticket", style=discord.ButtonStyle.primary, emoji="🎫")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        await create_ticket_channel(interaction, "Opened from the ticket panel")


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
        category = guild.get_channel(int(cat_id))  # type: ignore[arg-type]
    name = f"ticket-{user.name.lower().replace(' ', '-')}"[:90]
    channel = await guild.create_text_channel(name, category=category, overwrites=overwrites,
                                              topic=f"Ticket for {user} | {reason}"[:200])
    db.add_row("tickets", guild_id=guild.id, channel_id=channel.id, owner_id=user.id,
               status="open", reason=reason, claimed_by=None, created_at=db.now())
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
        channel = await create_ticket_channel(interaction, reason)
        await interaction.followup.send(f"Ticket created: {channel.mention}", ephemeral=True)

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
        await interaction.response.send_message(f"Closing ticket. Reason: {reason}. Channel will be deleted in a moment.")
        await interaction.channel.delete(reason=f"Ticket closed: {reason}")  # type: ignore[union-attr]

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
    @app_commands.command(name="faq", description="Look up a FAQ topic")
    async def faq(self, interaction: discord.Interaction, topic: str):
        with db._conn() as conn:
            row = conn.execute("SELECT * FROM faqs WHERE guild_id IN (0, ?) AND topic=?",
                               (interaction.guild.id, topic.lower())).fetchone()
        if not row:
            await interaction.response.send_message(f"No FAQ for '{topic}'. Try /faq_list.", ephemeral=True); return
        await interaction.response.send_message(embed=emb(f"FAQ: {topic}", row["answer"]), ephemeral=True)

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

    @app_commands.command(name="helpdesk", description="Show how to get help on this server")
    async def helpdesk(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=emb(
            "Helpdesk", "1. Use /ticket_create for private help.\n2. Use /faq for common questions.\n"
            "3. Use /report to report a problem user.\n4. Use /staff_ping only for urgent issues."),
            ephemeral=True)

    @app_commands.command(name="staff_ping", description="Ping support staff for an urgent issue")
    async def staff_ping(self, interaction: discord.Interaction, issue: str):
        mentions = " ".join(r.mention for r in support_roles(interaction.guild)) or "staff"
        await interaction.response.send_message(f"{mentions} Urgent help requested by {interaction.user.mention}: {issue}")

    # ---- reports / suggestions / bugs / appeals / feedback ----
    @app_commands.command(name="report", description="Report a member to staff")
    async def report(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        rid = db.add_row("reports", guild_id=interaction.guild.id, reporter_id=interaction.user.id,
                         target_id=member.id, reason=reason, created_at=db.now())
        await interaction.response.send_message(f"Report #{rid} filed against {member.mention}. Staff will review it.", ephemeral=True)

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
        await interaction.response.send_message(f"Suggestion #{sid} recorded. Thanks!", ephemeral=True)

    @app_commands.command(name="suggestion_list", description="List recent suggestions")
    async def suggestion_list(self, interaction: discord.Interaction):
        rows = db.list_rows("suggestions", interaction.guild.id, 20)
        text = "\n".join(f"#{r['id']} by <@{r['author_id']}>: {r['text']}" for r in rows) or "No suggestions."
        await interaction.response.send_message(embed=emb("Suggestions", text), ephemeral=True)

    @app_commands.command(name="bug", description="Report a bug in the server or bot")
    async def bug(self, interaction: discord.Interaction, description: str):
        bid = db.add_row("bugs", guild_id=interaction.guild.id, author_id=interaction.user.id,
                         text=description, created_at=db.now())
        await interaction.response.send_message(f"Bug #{bid} recorded. Thanks for reporting it.", ephemeral=True)

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
        await interaction.response.send_message(f"Appeal #{aid} filed. Staff will review it.", ephemeral=True)

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
