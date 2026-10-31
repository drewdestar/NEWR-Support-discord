"""Community cog: famous-bot style features, as 8 top-level groups.

Each GroupCog counts as ONE top-level slash command in Discord's
100-command guild cap, no matter how many subcommands it holds.
That is why these features are groups, not 20+ new flat commands.

Groups: /level, /giveaway, /poll, /reactionrole, /welcome, /afk,
/invites, /autorole.

All state lives in the bot's SQLite data.db (same file as tickets etc).
No real money, no paid APIs, no image generation here.
"""
from __future__ import annotations

import random
import sqlite3
import time
from datetime import datetime, timezone

import discord
from cogs.emoji import partial
from cogs.ui import denied as _denied
from discord import app_commands
from discord.ext import commands

import db
from roles import is_staff


def emb(title: str, desc: str) -> discord.Embed:
    from cogs.ui import panel
    return panel(title, desc, 0x57F287)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables() -> None:
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS levels(
            guild_id INTEGER, user_id INTEGER, xp INTEGER DEFAULT 0,
            last_xp INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id));
        CREATE TABLE IF NOT EXISTS giveaways(
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            channel_id INTEGER, message_id INTEGER, prize TEXT,
            winners INTEGER, ended INTEGER DEFAULT 0, created_at TEXT);
        CREATE TABLE IF NOT EXISTS giveaway_entries(
            giveaway_id INTEGER, user_id INTEGER,
            PRIMARY KEY (giveaway_id, user_id));
        CREATE TABLE IF NOT EXISTS polls(
            message_id INTEGER PRIMARY KEY, guild_id INTEGER,
            question TEXT, options TEXT);
        CREATE TABLE IF NOT EXISTS poll_votes(
            message_id INTEGER, user_id INTEGER, option_index INTEGER,
            PRIMARY KEY (message_id, user_id));
        CREATE TABLE IF NOT EXISTS reaction_roles(
            message_id INTEGER PRIMARY KEY, guild_id INTEGER, role_id INTEGER);
        CREATE TABLE IF NOT EXISTS role_menus(
            message_id INTEGER PRIMARY KEY, guild_id INTEGER, roles TEXT);
        CREATE TABLE IF NOT EXISTS afk(
            guild_id INTEGER, user_id INTEGER, reason TEXT,
            PRIMARY KEY (guild_id, user_id));
        """)


def _level_for_xp(xp: int) -> int:
    lvl = 0
    while (lvl + 1) * (lvl + 1) * 100 <= xp:
        lvl += 1
    return lvl


def _staff(i: discord.Interaction) -> bool:
    return is_staff(i.user)  # type: ignore[arg-type]


# ---- persistent button views (fixed custom_ids, so they survive restarts) ----

class GiveawayJoinView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Join Giveaway", style=discord.ButtonStyle.primary,
                       emoji=partial("newr_party"), custom_id="newr_giveaway_join")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        _ensure_tables()
        with _conn() as conn:
            row = conn.execute(
                "SELECT id, ended FROM giveaways WHERE message_id=?",
                (interaction.message.id,)).fetchone()
            if row is None or row["ended"]:
                await interaction.response.send_message(
                    "This giveaway is over.", ephemeral=True); return
            conn.execute("INSERT OR IGNORE INTO giveaway_entries VALUES (?, ?)",
                         (row["id"], interaction.user.id))
        await interaction.response.send_message(
            "You entered the giveaway! Good luck.", ephemeral=True)


class ReactionRoleView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Get Role", style=discord.ButtonStyle.success,
                       emoji=partial("newr_check"), custom_id="newr_reactionrole_toggle")
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        _ensure_tables()
        with _conn() as conn:
            row = conn.execute(
                "SELECT role_id FROM reaction_roles WHERE message_id=?",
                (interaction.message.id,)).fetchone()
        if row is None:
            await interaction.response.send_message(
                "No role is linked to this message anymore.", ephemeral=True); return
        role = interaction.guild.get_role(row["role_id"])  # type: ignore[union-attr]
        member = interaction.user  # type: ignore[assignment]
        if role is None:
            await interaction.response.send_message(
                "That role no longer exists.", ephemeral=True); return
        try:
            if role in member.roles:  # type: ignore[attr-defined]
                await member.remove_roles(role)  # type: ignore[attr-defined]
                await interaction.response.send_message(
                    f"Removed role {role.mention}.", ephemeral=True)
            else:
                await member.add_roles(role)  # type: ignore[attr-defined]
                await interaction.response.send_message(
                    f"Added role {role.mention}.", ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message(
                "I could not change your roles. Check my permissions and role position.",
                ephemeral=True)


class PollView(discord.ui.View):
    """Per-poll view (buttons are labelled by option). Not persistent:
    polls are short-lived, and /poll results reads the stored votes."""
    def __init__(self, options: list[str], message_id: int) -> None:
        super().__init__(timeout=None)
        self._options = options
        self._message_id = message_id
        for idx, opt in enumerate(options):
            button = discord.ui.Button(label=opt[:80],
                                       style=discord.ButtonStyle.secondary,
                                       custom_id=f"newr_poll_{message_id}_{idx}")
            button.callback = self._make_callback(idx)  # type: ignore[method-assign]
            self.add_item(button)

    def _make_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            _ensure_tables()
            with _conn() as conn:
                conn.execute(
                    "INSERT INTO poll_votes VALUES (?, ?, ?) "
                    "ON CONFLICT(message_id, user_id) DO UPDATE SET option_index=excluded.option_index",
                    (self._message_id, interaction.user.id, idx))
            await interaction.response.send_message(
                f"Voted for: {self._options[idx]}", ephemeral=True)
        return callback


# ---- groups ----

class LevelGroup(commands.GroupCog, group_name="level",
                 group_description="XP, rank and leaderboard (MEE6-style)"):
    @app_commands.command(name="rank", description="Show a member's level and XP")
    async def rank(self, interaction: discord.Interaction,
                   member: discord.Member | None = None):
        member = member or interaction.user  # type: ignore[assignment]
        _ensure_tables()
        with _conn() as conn:
            row = conn.execute(
                "SELECT xp FROM levels WHERE guild_id=? AND user_id=?",
                (interaction.guild_id, member.id)).fetchone()
        xp = row["xp"] if row else 0
        lvl = _level_for_xp(xp)
        nxt = (lvl + 1) * (lvl + 1) * 100
        await interaction.response.send_message(
            embed=emb(f"Rank: {member.display_name}",
                      f"Level {lvl}\nXP: {xp} / {nxt} for next level"), ephemeral=True)

    @app_commands.command(name="leaderboard", description="Top members by XP")
    async def leaderboard(self, interaction: discord.Interaction):
        _ensure_tables()
        with _conn() as conn:
            rows = conn.execute(
                "SELECT user_id, xp FROM levels WHERE guild_id=? ORDER BY xp DESC LIMIT 10",
                (interaction.guild_id,)).fetchall()
        lines = []
        for i, r in enumerate(rows, 1):
            lines.append(f"{i}. <@{r['user_id']}> — Level {_level_for_xp(r['xp'])} ({r['xp']} XP)")
        await interaction.response.send_message(
            embed=emb("XP Leaderboard", "\n".join(lines) or "No XP yet. Chat to earn XP."),
            ephemeral=True)

    @app_commands.command(name="addxp", description="Give XP to a member (staff)")
    async def addxp(self, interaction: discord.Interaction,
                    member: discord.Member, amount: int):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        amount = max(0, min(10000, amount))
        _ensure_tables()
        with _conn() as conn:
            conn.execute(
                "INSERT INTO levels VALUES (?, ?, ?, 0) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=xp+excluded.xp",
                (interaction.guild_id, member.id, amount))
        await interaction.response.send_message(
            f"Gave {amount} XP to {member.mention}.", ephemeral=True)


class GiveawayGroup(commands.GroupCog, group_name="giveaway",
                    group_description="Create, end and reroll giveaways"):
    @app_commands.command(name="create", description="Create a giveaway (staff)")
    async def create(self, interaction: discord.Interaction, prize: str,
                     minutes: int, winners: int = 1):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        minutes = max(1, min(10080, minutes))
        winners = max(1, min(10, winners))
        _ensure_tables()
        gid = db.add_row("giveaways", guild_id=interaction.guild_id,
                         channel_id=interaction.channel_id, message_id=0,
                         prize=prize, winners=winners, ended=0,
                         created_at=db.now())
        msg = await interaction.channel.send(  # type: ignore[union-attr]
            embed=emb(f"🎉 Giveaway: {prize}",
                      f"Click Join below! Winners: {winners}\n"
                      f"Ends in {minutes} minutes — staff end it with /giveaway end."),
            view=GiveawayJoinView())
        with _conn() as conn:
            conn.execute("UPDATE giveaways SET message_id=? WHERE id=?", (msg.id, gid))
        await interaction.response.send_message(
            f"Giveaway created: {prize} (id {gid}).", ephemeral=True)

    async def _pick(self, interaction: discord.Interaction, gid: int):
        with _conn() as conn:
            gw = conn.execute("SELECT * FROM giveaways WHERE id=? AND guild_id=?",
                              (gid, interaction.guild_id)).fetchone()
            if gw is None:
                return None, []
            entries = conn.execute(
                "SELECT user_id FROM giveaway_entries WHERE giveaway_id=?", (gid,)).fetchall()
        winners = random.sample([r["user_id"] for r in entries],
                                min(gw["winners"], len(entries))) if entries else []
        return gw, winners

    @app_commands.command(name="end", description="End a giveaway and pick winners (staff)")
    async def end(self, interaction: discord.Interaction, giveaway_id: int):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        gw, winners = await self._pick(interaction, giveaway_id)
        if gw is None:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True); return
        with _conn() as conn:
            conn.execute("UPDATE giveaways SET ended=1 WHERE id=?", (giveaway_id,))
        text = (f"🎉 Giveaway ended: **{gw['prize']}**\nWinners: "
                + (", ".join(f"<@{u}>" for u in winners) if winners else "no entries"))
        await interaction.response.send_message(text)

    @app_commands.command(name="reroll", description="Pick new winners for an ended giveaway (staff)")
    async def reroll(self, interaction: discord.Interaction, giveaway_id: int):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        gw, winners = await self._pick(interaction, giveaway_id)
        if gw is None:
            await interaction.response.send_message("Giveaway not found.", ephemeral=True); return
        text = (f"🎉 Giveaway rerolled: **{gw['prize']}**\nNew winners: "
                + (", ".join(f"<@{u}>" for u in winners) if winners else "no entries"))
        await interaction.response.send_message(text)


class PollGroup(commands.GroupCog, group_name="poll",
                group_description="Create polls and see results"):
    @app_commands.command(name="create", description="Create a poll with buttons")
    async def create(self, interaction: discord.Interaction, question: str,
                     option1: str, option2: str,
                     option3: str = "", option4: str = ""):
        options = [o for o in (option1, option2, option3, option4) if o]
        _ensure_tables()
        msg = await interaction.channel.send(  # type: ignore[union-attr]
            embed=emb(f"📊 {question}",
                      "\n".join(f"{i + 1}. {o}" for i, o in enumerate(options))))
        with _conn() as conn:
            conn.execute("INSERT INTO polls VALUES (?, ?, ?, ?)",
                         (msg.id, interaction.guild_id, question, "\n".join(options)))
        # Attach the voting view to the same message.
        await msg.edit(view=PollView(options, msg.id))
        await interaction.response.send_message("Poll created.", ephemeral=True)

    @app_commands.command(name="results", description="Show results for a poll message")
    async def results(self, interaction: discord.Interaction, message_id: str):
        _ensure_tables()
        try:
            mid = int(message_id)
        except ValueError:
            await interaction.response.send_message("message_id must be a number.", ephemeral=True); return
        with _conn() as conn:
            poll = conn.execute("SELECT * FROM polls WHERE message_id=?", (mid,)).fetchone()
            votes = conn.execute(
                "SELECT option_index, COUNT(*) c FROM poll_votes WHERE message_id=? GROUP BY option_index",
                (mid,)).fetchall() if poll else []
        if poll is None:
            await interaction.response.send_message("Poll not found.", ephemeral=True); return
        options = poll["options"].split("\n")
        counts = {r["option_index"]: r["c"] for r in votes}
        lines = [f"{i + 1}. {o} — {counts.get(i, 0)} vote(s)"
                 for i, o in enumerate(options)]
        await interaction.response.send_message(
            embed=emb(f"📊 Results: {poll['question']}", "\n".join(lines)), ephemeral=True)


class RoleMenuSelectView(discord.ui.View):
    """YAGPDB-style role menu, Single mode: pick one role at a time.

    One select, custom_id newr_rolemenu_select, registered persistently
    in bot.py. The options shown on a posted message are that menu's
    roles; on click, the callback reads the menu's roles from the
    role_menus table by message id, removes all other menu roles
    from the member, and adds the selected one. Selecting the role
    you already have removes it (toggle-off).
    """
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.select(placeholder="Choose a role", custom_id="newr_rolemenu_select",
                       options=[discord.SelectOption(label="Choose a role", value="0")])
    async def choose(self, interaction: discord.Interaction, select: discord.ui.Select):  # noqa: ARG002
        _ensure_tables()
        with _conn() as conn:
            row = conn.execute("SELECT roles FROM role_menus WHERE message_id=?",
                               (interaction.message.id,)).fetchone()
        if row is None:
            await interaction.response.send_message("This role menu no longer exists.", ephemeral=True); return
        import json as _json
        role_ids = _json.loads(row["roles"])
        chosen_id = int(select.values[0])
        guild = interaction.guild
        member = interaction.user  # type: ignore[assignment]
        to_remove, chosen = [], None
        for rid in role_ids:
            role = guild.get_role(rid)  # type: ignore[union-attr]
            if role is None:
                continue
            if rid == chosen_id:
                chosen = role
            elif role in member.roles:  # type: ignore[attr-defined]
                to_remove.append(role)
        if chosen is None:
            await interaction.response.send_message("That role no longer exists.", ephemeral=True); return
        try:
            if to_remove:
                await member.remove_roles(*to_remove, reason="Role menu (single mode)")  # type: ignore[attr-defined]
            if chosen in member.roles:  # type: ignore[attr-defined]
                await member.remove_roles(chosen, reason="Role menu (single mode)")  # type: ignore[attr-defined]
                await interaction.response.send_message(f"Removed {chosen.mention}.", ephemeral=True)
            else:
                await member.add_roles(chosen, reason="Role menu (single mode)")  # type: ignore[attr-defined]
                await interaction.response.send_message(f"You now have {chosen.mention}.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Could not change roles: {e}", ephemeral=True)


class ReactionRoleGroup(commands.GroupCog, group_name="reactionrole",
                        group_description="Button roles (Carl-bot style)"):
    @app_commands.command(name="menu", description="Post a single-mode role menu: pick one role at a time (staff, YAGPDB-style)")
    @app_commands.describe(role1="First role in the menu", role2="Second role (optional)",
                           role3="Third role (optional)", role4="Fourth role (optional)",
                           role5="Fifth role (optional)", title="Menu title")
    async def menu(self, interaction: discord.Interaction, role1: discord.Role,
                   role2: discord.Role | None = None, role3: discord.Role | None = None,
                   role4: discord.Role | None = None, role5: discord.Role | None = None,
                   title: str = "Choose a Role"):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        roles = [r for r in (role1, role2, role3, role4, role5) if r is not None]
        _ensure_tables()
        options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in roles]
        view = RoleMenuSelectView()
        # Replace the placeholder option with this menu's roles.
        view.children[0].options = options  # type: ignore[attr-defined]
        msg = await interaction.channel.send(  # type: ignore[union-attr]
            embed=emb(title, "Pick one role from the menu below. Picking another role removes the previous one."),
            view=view)
        import json as _json
        with _conn() as conn:
            conn.execute("INSERT INTO role_menus VALUES (?, ?, ?)",
                         (msg.id, interaction.guild_id, _json.dumps([r.id for r in roles])))
        await interaction.response.send_message("Role menu posted.", ephemeral=True)

    @app_commands.command(name="post", description="Post a button that toggles a role (staff)")
    async def post(self, interaction: discord.Interaction, role: discord.Role,
                   label: str = "Get Role"):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        _ensure_tables()
        msg = await interaction.channel.send(  # type: ignore[union-attr]
            embed=emb(f"Role: {role.name}", f"Click the button to toggle {role.mention}."),
            view=ReactionRoleView())
        with _conn() as conn:
            conn.execute("INSERT INTO reaction_roles VALUES (?, ?, ?)",
                         (msg.id, interaction.guild_id, role.id))
        await interaction.response.send_message("Reaction-role button posted.", ephemeral=True)

    @app_commands.command(name="list", description="List reaction-role messages")
    async def list_roles(self, interaction: discord.Interaction):
        _ensure_tables()
        with _conn() as conn:
            rows = conn.execute(
                "SELECT message_id, role_id FROM reaction_roles WHERE guild_id=? ORDER BY message_id DESC LIMIT 20",
                (interaction.guild_id,)).fetchall()
        lines = [f"Message {r['message_id']} — <@&{r['role_id']}>" for r in rows]
        await interaction.response.send_message(
            embed=emb("Reaction Roles", "\n".join(lines) or "None yet."), ephemeral=True)


class WelcomeGroup(commands.GroupCog, group_name="welcome",
                   group_description="Welcome and goodbye messages"):
    @app_commands.command(name="set", description="Set the welcome channel and message (staff)")
    async def set_welcome(self, interaction: discord.Interaction,
                          channel: discord.TextChannel, message: str):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        db.set_setting(interaction.guild_id, "welcome_channel", str(channel.id))
        db.set_setting(interaction.guild_id, "welcome_message", message)
        await interaction.response.send_message(
            f"Welcome messages will go to {channel.mention}.", ephemeral=True)

    @app_commands.command(name="disable", description="Turn off welcome messages (staff)")
    async def disable(self, interaction: discord.Interaction):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        db.set_setting(interaction.guild_id, "welcome_channel", "0")
        await interaction.response.send_message("Welcome messages disabled.", ephemeral=True)

    @app_commands.command(name="show", description="Show the current welcome setup")
    async def show(self, interaction: discord.Interaction):
        ch = db.get_setting(interaction.guild_id, "welcome_channel", "0")
        msg = db.get_setting(interaction.guild_id, "welcome_message", "")
        await interaction.response.send_message(
            f"Channel: <#{ch}> if set (raw: {ch})\nMessage: {msg or '(not set)'}\n"
            "Use {user} for the new member's mention in the message.", ephemeral=True)


class AfkGroup(commands.GroupCog, group_name="afk",
               group_description="AFK status that auto-replies on mentions"):
    @app_commands.command(name="set", description="Mark yourself AFK with a reason")
    async def set_afk(self, interaction: discord.Interaction, reason: str = "AFK"):
        _ensure_tables()
        with _conn() as conn:
            conn.execute(
                "INSERT INTO afk VALUES (?, ?, ?) "
                "ON CONFLICT(guild_id, user_id) DO UPDATE SET reason=excluded.reason",
                (interaction.guild_id, interaction.user.id, reason))
        await interaction.response.send_message(f"You are now AFK: {reason}", ephemeral=True)

    @app_commands.command(name="back", description="Clear your AFK status")
    async def back(self, interaction: discord.Interaction):
        _ensure_tables()
        with _conn() as conn:
            conn.execute("DELETE FROM afk WHERE guild_id=? AND user_id=?",
                         (interaction.guild_id, interaction.user.id))
        await interaction.response.send_message("Welcome back! AFK cleared.", ephemeral=True)

    @app_commands.command(name="list", description="List members currently AFK")
    async def list_afk(self, interaction: discord.Interaction):
        _ensure_tables()
        with _conn() as conn:
            rows = conn.execute(
                "SELECT user_id, reason FROM afk WHERE guild_id=? LIMIT 20",
                (interaction.guild_id,)).fetchall()
        lines = [f"<@{r['user_id']}> — {r['reason']}" for r in rows]
        await interaction.response.send_message(
            embed=emb("AFK Members", "\n".join(lines) or "Nobody is AFK."), ephemeral=True)


class InvitesGroup(commands.GroupCog, group_name="invites",
                   group_description="Invite tracking and leaderboard"):
    @app_commands.command(name="leaderboard", description="Top inviters on this server")
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            invites = await interaction.guild.invites()  # type: ignore[union-attr]
        except discord.HTTPException:
            await interaction.followup.send(
                "I cannot read invites. Give me Manage Server / Manage Channels permission.",
                ephemeral=True); return
        totals: dict[int, int] = {}
        for inv in invites:
            if inv.inviter:
                totals[inv.inviter.id] = totals.get(inv.inviter.id, 0) + inv.uses
        top = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:10]
        lines = [f"{i}. <@{uid}> — {n} invite(s)" for i, (uid, n) in enumerate(top, 1)]
        await interaction.followup.send(
            embed=emb("Invite Leaderboard", "\n".join(lines) or "No invites found."),
            ephemeral=True)

    @app_commands.command(name="mine", description="How many people you invited")
    async def mine(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            invites = await interaction.guild.invites()  # type: ignore[union-attr]
        except discord.HTTPException:
            await interaction.followup.send(
                "I cannot read invites. Give me Manage Server / Manage Channels permission.",
                ephemeral=True); return
        total = sum(inv.uses for inv in invites
                    if inv.inviter and inv.inviter.id == interaction.user.id)
        await interaction.followup.send(
            f"You have invited {total} member(s) (by current invite uses).", ephemeral=True)


class AutoroleGroup(commands.GroupCog, group_name="autorole",
                    group_description="Automatic role for new members"):
    @app_commands.command(name="set", description="Set the role new members get (staff)")
    async def set_autorole(self, interaction: discord.Interaction, role: discord.Role):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        db.set_setting(interaction.guild_id, "autorole_role", str(role.id))
        await interaction.response.send_message(
            f"New members will get {role.mention}.", ephemeral=True)

    @app_commands.command(name="disable", description="Turn off autorole (staff)")
    async def disable(self, interaction: discord.Interaction):
        if not _staff(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        db.set_setting(interaction.guild_id, "autorole_role", "0")
        await interaction.response.send_message("Autorole disabled.", ephemeral=True)

    @app_commands.command(name="show", description="Show the current autorole")
    async def show(self, interaction: discord.Interaction):
        rid = db.get_setting(interaction.guild_id, "autorole_role", "0")
        await interaction.response.send_message(
            f"Autorole: <@&{rid}>" if rid != "0" else "Autorole is not set.", ephemeral=True)


class Community(commands.Cog):
    """Listeners shared by the groups: XP, welcome/autorole on join, AFK."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._xp_cooldown: dict[tuple[int, int], float] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        _ensure_tables()
        # XP: 5-15 per message, max once per 60s per user.
        key = (message.guild.id, message.author.id)
        now_ts = time.time()
        if now_ts - self._xp_cooldown.get(key, 0) >= 60:
            self._xp_cooldown[key] = now_ts
            with _conn() as conn:
                conn.execute(
                    "INSERT INTO levels VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=xp+excluded.xp, last_xp=excluded.last_xp",
                    (message.guild.id, message.author.id,
                     random.randint(5, 15), int(now_ts)))
        # AFK: clear on the author's own message, notify on mentions.
        with _conn() as conn:
            conn.execute("DELETE FROM afk WHERE guild_id=? AND user_id=?",
                         (message.guild.id, message.author.id))
            afk_users = {r["user_id"]: r["reason"] for r in conn.execute(
                "SELECT user_id, reason FROM afk WHERE guild_id=?",
                (message.guild.id,)).fetchall()}
        for mentioned in message.mentions:
            if mentioned.id in afk_users:
                await message.channel.send(
                    f"{mentioned.mention} is AFK: {afk_users[mentioned.id]}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        # Autorole
        rid = db.get_setting(guild.id, "autorole_role", "0")
        if rid != "0":
            role = guild.get_role(int(rid))
            if role is not None:
                try:
                    await member.add_roles(role)
                except discord.HTTPException:
                    pass
        # Welcome
        ch_id = db.get_setting(guild.id, "welcome_channel", "0")
        if ch_id != "0":
            ch = guild.get_channel(int(ch_id))
            msg = db.get_setting(guild.id, "welcome_message", "")
            if ch is not None and isinstance(ch, discord.TextChannel):
                text = (msg or "Welcome {user} to the server!").replace("{user}", member.mention)
                try:
                    await ch.send(text)
                except discord.HTTPException:
                    pass


async def setup(bot: commands.Bot) -> None:
    _ensure_tables()
    await bot.add_cog(Community(bot))
    for group in (LevelGroup(), GiveawayGroup(), PollGroup(), ReactionRoleGroup(),
                  WelcomeGroup(), AfkGroup(), InvitesGroup(), AutoroleGroup()):
        await bot.add_cog(group)
