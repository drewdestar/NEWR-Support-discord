"""Server backup and restore for NEWR Support.

Why this exists: if the server is deleted or raided (channels/roles
wiped), the owner can create a fresh server, invite this bot, and
restore the last backup there. A backup is one JSON file in
~/workspace/bots/newr-support/backups/ containing:

- Server structure: roles (name, colour, permissions, hoist,
  mentionable, position), categories and channels (name, category,
  position, topic, slowmode, NSFW, voice bitrate/user limit, and
  permission overwrites mapped by ROLE NAME, not by ID, so they
  survive into a new server), custom emojis (name + image URL),
  and guild system settings (verification level, notification
  level, content filter, AFK timeout, AFK/system/rules channels
  referenced by name).
- Bot data for that guild: warns, reports, appeals, tickets,
  suggestions, bugs, feedback, notes, watchlist, banned words,
  FAQs, levels, AFK, reaction roles, polls, giveaways, settings
  (channel/role settings are stored with their resolved name so
  they can be re-pointed at the new channels/roles), and bans.
- Members: every human member's user ID, nickname, and role names.
  On restore, roles/nicknames are re-applied to members who are
  already in the new server. The bot cannot invite people back
  (Discord does not allow that) — members must rejoin themselves,
  then their old warns/reports still follow them by user ID,
  because bot data is restored by user ID, not by guild.

Restore is NON-DESTRUCTIVE by design: it never deletes existing
channels or roles. It reuses anything that already exists by name
and creates what is missing, then updates overwrites/topics.
That makes it safe to run into a fresh server (only a few default
channels) and also safe to run into a partially-raided server.

Slash slot: Discord caps a guild at 100 top-level commands and
this bot was already at 100, so /backup is a group (1 top-level
slot, 4 subcommands) replacing the redundant /command_list
(/help already lists every command).

Owner-only restore: /backup restore can rewrite the whole
structure, so only the guild owner may run it, and it requires
typing RESTORE as confirmation. Create/list/auto are staff-only.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import discord
from cogs.ui import denied as _denied
from discord import app_commands
from discord.ext import commands, tasks

import db
from roles import is_staff

BACKUP_DIR = Path(__file__).resolve().parent.parent / "backups"
# DB tables copied into a backup (all have a guild_id column).
BOT_TABLES = ["warns", "reports", "appeals", "tickets", "suggestions",
              "bugs", "feedback", "notes", "watchlist", "banned_words",
              "faqs", "levels", "afk", "reaction_roles", "polls",
              "poll_votes", "giveaways", "giveaway_entries", "settings",
              "dm_requests", "command_offenses", "applications"]
# Settings whose value is a channel/role ID: store the resolved name
# too, so restore can re-point them at the new server's channels.
CHANNEL_SETTINGS = {"log_channel", "report_channel", "appeal_channel",
                    "welcome_channel"}
ROLE_SETTINGS = {"autorole_role"}


def _overwrites(channel) -> list[dict]:
    out = []
    for target, ow in channel.overwrites.items():
        if isinstance(target, discord.Role):
            kind, name = "role", target.name
        elif isinstance(target, discord.Member):
            kind, name = "member", str(target.id)
        else:
            continue
        out.append({"kind": kind, "name": name,
                    "allow": ow.pair()[0].value, "deny": ow.pair()[1].value})
    return out


def _role_data(role: discord.Role) -> dict:
    return {"name": role.name, "colour": role.colour.value,
            "permissions": role.permissions.value, "hoist": role.hoist,
            "mentionable": role.mentionable, "position": role.position}


async def create_snapshot(guild: discord.Guild, author_id: int) -> dict:
    """Build the full backup dict for a guild. No file written yet."""
    roles = [_role_data(r) for r in sorted(guild.roles, key=lambda r: r.position)]
    categories = []
    for cat in sorted(guild.categories, key=lambda c: c.position):
        categories.append({"name": cat.name, "position": cat.position,
                           "overwrites": _overwrites(cat)})
    text_channels, voice_channels = [], []
    for ch in sorted(guild.text_channels, key=lambda c: c.position):
        text_channels.append({"name": ch.name,
                              "category": ch.category.name if ch.category else None,
                              "position": ch.position, "topic": ch.topic,
                              "slowmode": ch.slowmode_delay, "nsfw": ch.nsfw,
                              "overwrites": _overwrites(ch)})
    for ch in sorted(guild.voice_channels, key=lambda c: c.position):
        voice_channels.append({"name": ch.name,
                               "category": ch.category.name if ch.category else None,
                               "position": ch.position, "bitrate": ch.bitrate,
                               "user_limit": ch.user_limit,
                               "overwrites": _overwrites(ch)})
    emojis = [{"name": e.name, "url": str(e.url), "animated": e.animated}
              for e in guild.emojis]
    # Members: fetch so the snapshot is complete, not just the cache.
    members = []
    try:
        async for m in guild.fetch_members(limit=None):
            if m.bot:
                continue
            members.append({"user_id": m.id, "nick": m.nick,
                            "roles": [r.name for r in m.roles if r.name != "@everyone"]})
    except Exception:
        members = [{"user_id": m.id, "nick": m.nick,
                    "roles": [r.name for r in m.roles if r.name != "@everyone"]}
                   for m in guild.members if not m.bot]
    bans = []
    try:
        async for entry in guild.bans(limit=None):
            bans.append({"user_id": entry.user.id, "reason": entry.reason})
    except Exception:
        pass
    system = {
        "verification_level": str(guild.verification_level),
        "default_notifications": str(guild.default_notifications),
        "explicit_content_filter": str(guild.explicit_content_filter),
        "afk_timeout": guild.afk_timeout,
        "afk_channel": guild.afk_channel.name if guild.afk_channel else None,
        "system_channel": guild.system_channel.name if guild.system_channel else None,
        "rules_channel": guild.rules_channel.name if guild.rules_channel else None,
    }
    bot_data: dict[str, list] = {}
    with db._conn() as conn:
        for table in BOT_TABLES:
            try:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE guild_id=?", (guild.id,)).fetchall()
                bot_data[table] = [dict(r) for r in rows]
            except Exception:
                bot_data[table] = {}
    # Resolve channel/role settings to names for re-pointing on restore.
    settings = bot_data.get("settings", [])
    for row in settings:
        key, val = row.get("key"), row.get("value")
        try:
            if key in CHANNEL_SETTINGS and val and val != "0":
                ch = guild.get_channel(int(val))
                row["resolved_name"] = ch.name if ch else None
            elif key in ROLE_SETTINGS and val and val != "0":
                role = guild.get_role(int(val))
                row["resolved_name"] = role.name if role else None
        except Exception:
            row["resolved_name"] = None
    return {
        "version": 1, "guild_id": guild.id, "guild_name": guild.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": author_id,
        "roles": roles, "categories": categories,
        "text_channels": text_channels, "voice_channels": voice_channels,
        "emojis": emojis, "members": members, "bans": bans,
        "system": system, "bot_data": bot_data,
    }


def _backup_path(data: dict) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return BACKUP_DIR / f"{data['guild_id']}_{stamp}.json"


def _list_backups() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("*.json"),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def _load_backup(backup_id: str) -> tuple[Path | None, dict | None]:
    for p in _list_backups():
        if p.stem == backup_id or p.name == backup_id:
            try:
                return p, json.loads(p.read_text())
            except Exception:
                return p, None
    return None, None


def _prune(guild_id: int, keep: int = 10) -> None:
    """Keep only the newest `keep` backups for one guild."""
    files = [p for p in _list_backups()
             if p.name.startswith(f"{guild_id}_")]
    for old in files[keep:]:
        try:
            old.unlink()
        except Exception:
            pass


async def restore_snapshot(guild: discord.Guild, data: dict) -> dict:
    """Restore a snapshot into `guild` (non-destructive). Returns counts."""
    counts = {"roles_created": 0, "roles_reused": 0,
              "categories_created": 0, "channels_created": 0,
              "channels_reused": 0, "emojis_created": 0,
              "members_updated": 0, "bans_restored": 0,
              "bot_rows": 0, "failed": []}
    bot_member = guild.me
    # --- roles (create lowest first, fix positions at the end) ---
    role_map: dict[str, discord.Role] = {r.name: r for r in guild.roles}
    for rd in sorted(data.get("roles", []), key=lambda r: r["position"]):
        if rd["name"] == "@everyone":
            try:
                await guild.default_role.edit(
                    permissions=discord.Permissions(rd["permissions"]))
            except Exception as e:
                counts["failed"].append(f"@everyone permissions: {e}")
            continue
        if rd["name"] in role_map:
            counts["roles_reused"] += 1
            continue
        try:
            role = await guild.create_role(
                name=rd["name"], colour=discord.Colour(rd["colour"]),
                permissions=discord.Permissions(rd["permissions"]),
                hoist=rd["hoist"], mentionable=rd["mentionable"],
                reason="Backup restore")
            role_map[rd["name"]] = role
            counts["roles_created"] += 1
        except Exception as e:
            counts["failed"].append(f"role {rd['name']}: {e}")
    # Fix role positions (highest first so Discord accepts the order).
    try:
        positions = {role_map[rd["name"]]: rd["position"]
                     for rd in data.get("roles", [])
                     if rd["name"] in role_map and rd["name"] != "@everyone"}
        if positions:
            await guild.edit_role_positions(positions=positions)
    except Exception as e:
        counts["failed"].append(f"role positions: {e}")

    def _map_overwrites(ows: list[dict]) -> dict:
        out = {}
        for ow in ows:
            if ow["kind"] == "role":
                if ow["name"] == "@everyone":
                    out[guild.default_role] = discord.PermissionOverwrite.from_pair(
                        discord.Permissions(ow["allow"]), discord.Permissions(ow["deny"]))
                elif ow["name"] in role_map:
                    out[role_map[ow["name"]]] = discord.PermissionOverwrite.from_pair(
                        discord.Permissions(ow["allow"]), discord.Permissions(ow["deny"]))
            # Member overwrites are skipped: members may not be in the
            # new server, and a stale member overwrite would be noise.
        if bot_member is not None:
            out.setdefault(bot_member, discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                embed_links=True, attach_files=True))
        return out

    # --- categories ---
    cat_map: dict[str, discord.CategoryChannel] = {c.name: c for c in guild.categories}
    for cd in sorted(data.get("categories", []), key=lambda c: c["position"]):
        if cd["name"] in cat_map:
            try:
                await cat_map[cd["name"]].edit(overwrites=_map_overwrites(cd["overwrites"]))
            except Exception:
                pass
            continue
        try:
            cat_map[cd["name"]] = await guild.create_category(
                cd["name"], overwrites=_map_overwrites(cd["overwrites"]),
                reason="Backup restore")
            counts["categories_created"] += 1
        except Exception as e:
            counts["failed"].append(f"category {cd['name']}: {e}")
    # --- channels ---
    existing_text = {c.name: c for c in guild.text_channels}
    existing_voice = {c.name: c for c in guild.voice_channels}
    for cd in sorted(data.get("text_channels", []), key=lambda c: c["position"]):
        cat = cat_map.get(cd["category"]) if cd.get("category") else None
        if cd["name"] in existing_text:
            counts["channels_reused"] += 1
            try:
                await existing_text[cd["name"]].edit(
                    category=cat, topic=cd.get("topic"),
                    slowmode_delay=cd.get("slowmode") or 0, nsfw=bool(cd.get("nsfw")),
                    overwrites=_map_overwrites(cd["overwrites"]))
            except Exception:
                pass
            continue
        try:
            await guild.create_text_channel(
                cd["name"], category=cat, topic=cd.get("topic"),
                slowmode_delay=cd.get("slowmode") or 0, nsfw=bool(cd.get("nsfw")),
                overwrites=_map_overwrites(cd["overwrites"]), reason="Backup restore")
            counts["channels_created"] += 1
        except Exception as e:
            counts["failed"].append(f"channel #{cd['name']}: {e}")
    for cd in sorted(data.get("voice_channels", []), key=lambda c: c["position"]):
        cat = cat_map.get(cd["category"]) if cd.get("category") else None
        if cd["name"] in existing_voice:
            counts["channels_reused"] += 1
            continue
        try:
            await guild.create_voice_channel(
                cd["name"], category=cat, bitrate=cd.get("bitrate") or 64000,
                user_limit=cd.get("user_limit") or 0,
                overwrites=_map_overwrites(cd["overwrites"]), reason="Backup restore")
            counts["channels_created"] += 1
        except Exception as e:
            counts["failed"].append(f"voice {cd['name']}: {e}")
    # --- guild system settings ---
    sysd = data.get("system", {})
    try:
        kwargs: dict = {}
        if sysd.get("verification_level"):
            kwargs["verification_level"] = discord.VerificationLevel[
                sysd["verification_level"].split(".")[-1]]
        if sysd.get("default_notifications"):
            kwargs["default_notifications"] = discord.NotificationLevel[
                sysd["default_notifications"].split(".")[-1]]
        if sysd.get("explicit_content_filter"):
            kwargs["explicit_content_filter"] = discord.ContentFilter[
                sysd["explicit_content_filter"].split(".")[-1]]
        if sysd.get("afk_timeout"):
            kwargs["afk_timeout"] = int(sysd["afk_timeout"])
        if sysd.get("afk_channel"):
            ch = discord.utils.get(guild.voice_channels, name=sysd["afk_channel"])
            if ch:
                kwargs["afk_channel"] = ch
        if sysd.get("system_channel"):
            ch = discord.utils.get(guild.text_channels, name=sysd["system_channel"])
            if ch:
                kwargs["system_channel"] = ch
        if kwargs:
            await guild.edit(**kwargs)
    except Exception as e:
        counts["failed"].append(f"system settings: {e}")
    # --- emojis (best effort) ---
    try:
        import aiohttp
        existing_emoji = {e.name for e in guild.emojis}
        async with aiohttp.ClientSession(trust_env=True) as session:
            for ed in data.get("emojis", []):
                if ed["name"] in existing_emoji or len(guild.emojis) >= 50:
                    continue
                try:
                    async with session.get(ed["url"], timeout=15) as resp:
                        if resp.status == 200:
                            await guild.create_custom_emoji(
                                name=ed["name"], image=await resp.read(),
                                reason="Backup restore")
                            counts["emojis_created"] += 1
                except Exception:
                    pass
    except Exception:
        pass
    # --- bot data (replace target guild's rows, keyed by user ID) ---
    bot_data = data.get("bot_data", {})
    with db._conn() as conn:
        for table, rows in bot_data.items():
            if table not in BOT_TABLES or not isinstance(rows, list):
                continue
            try:
                conn.execute(f"DELETE FROM {table} WHERE guild_id=?", (guild.id,))
                for row in rows:
                    row = dict(row)
                    row["guild_id"] = guild.id
                    # Settings: re-point channel/role settings by name.
                    if table == "settings" and row.get("resolved_name"):
                        if row["key"] in CHANNEL_SETTINGS:
                            ch = (discord.utils.get(guild.text_channels, name=row["resolved_name"])
                                  or discord.utils.get(guild.voice_channels, name=row["resolved_name"]))
                            if ch:
                                row["value"] = str(ch.id)
                        elif row["key"] in ROLE_SETTINGS:
                            role = discord.utils.get(guild.roles, name=row["resolved_name"])
                            if role:
                                row["value"] = str(role.id)
                    row.pop("resolved_name", None)
                    cols = [c for c in row.keys() if c != "id"] if "id" in row else list(row.keys())
                    # Keep original IDs where the table has an id column
                    # that other tables reference (reports/appeals), so
                    # cross-references stay consistent; SQLite will
                    # accept explicit ids on a fresh guild.
                    placeholders = ", ".join("?" for _ in row)
                    conn.execute(
                        f"INSERT OR REPLACE INTO {table} ({', '.join(row.keys())}) "
                        f"VALUES ({placeholders})", list(row.values()))
                    counts["bot_rows"] += 1
            except Exception as e:
                counts["failed"].append(f"bot data {table}: {e}")
    # --- members: re-apply roles + nickname to members already here ---
    for md in data.get("members", []):
        member = guild.get_member(md["user_id"])
        if member is None:
            continue
        try:
            roles = [role_map[n] for n in md.get("roles", []) if n in role_map]
            if roles:
                await member.add_roles(*roles, reason="Backup restore")
            if md.get("nick") and member.nick != md["nick"]:
                await member.edit(nick=md["nick"], reason="Backup restore")
            counts["members_updated"] += 1
        except Exception:
            pass
    # --- bans ---
    for bd in data.get("bans", []):
        try:
            await guild.ban(discord.Object(id=bd["user_id"]),
                            reason=bd.get("reason") or "Backup restore")
            counts["bans_restored"] += 1
        except Exception:
            pass
    return counts


def _staff_only(i: discord.Interaction) -> bool:
    return is_staff(i.user)  # type: ignore[arg-type]


class BackupGroup(commands.GroupCog, group_name="backup",
                  group_description="Back up and restore the whole server"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.auto_loop.start()

    def cog_unload(self) -> None:
        self.auto_loop.cancel()

    @tasks.loop(hours=1)
    async def auto_loop(self) -> None:
        """Daily auto-backup for guilds with backup_auto=on."""
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            if db.get_setting(guild.id, "backup_auto", "off") != "on":
                continue
            try:
                data = await create_snapshot(guild, self.bot.user.id)
                path = _backup_path(data)
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                _prune(guild.id)
            except Exception:
                pass

    @app_commands.command(name="create", description="Create a full server backup now (staff)")
    async def create(self, interaction: discord.Interaction):
        if not _staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        data = await create_snapshot(interaction.guild, interaction.user.id)
        path = _backup_path(data)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        _prune(interaction.guild.id)
        await interaction.followup.send(
            f"✅ Backup created: `{path.stem}`\n"
            f"Roles: {len(data['roles'])}, Categories: {len(data['categories'])}, "
            f"Text: {len(data['text_channels'])}, Voice: {len(data['voice_channels'])}, "
            f"Emojis: {len(data['emojis'])}, Members: {len(data['members'])}, "
            f"Bans: {len(data['bans'])}, Bot data rows: "
            f"{sum(len(v) for v in data['bot_data'].values() if isinstance(v, list))}\n"
            f"Created from: {data['guild_name']} (ID {data['guild_id']}). "
            f"Restore it with `/backup restore` — owner only, with RESTORE confirmation.",
            ephemeral=True)

    @app_commands.command(name="list", description="List available backups (staff)")
    async def list_backups(self, interaction: discord.Interaction):
        if not _staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        files = _list_backups()[:10]
        if not files:
            await interaction.response.send_message("No backups yet. Use /backup create.", ephemeral=True); return
        lines = []
        for p in files:
            try:
                d = json.loads(p.read_text())
                lines.append(f"`{p.stem}` — {d.get('guild_name', '?')} — "
                             f"{d.get('created_at', '?')[:19]} — "
                             f"{len(d.get('roles', []))} roles, "
                             f"{len(d.get('text_channels', [])) + len(d.get('voice_channels', []))} channels")
            except Exception:
                lines.append(f"`{p.stem}` — unreadable")
        await interaction.response.send_message(
            "📦 **Backups (newest first):**\n" + "\n".join(lines), ephemeral=True)

    @app_commands.command(name="restore", description="Restore a backup into THIS server (owner only)")
    @app_commands.describe(backup_id="Backup ID from /backup list (the filename without .json)",
                           confirm="Type RESTORE to confirm — this rewrites roles/channels/bot data")
    async def restore(self, interaction: discord.Interaction, backup_id: str, confirm: str = ""):
        if interaction.guild.owner_id != interaction.user.id:
            await interaction.response.send_message(
                "Only the server owner can restore a backup.", ephemeral=True); return
        path, data = _load_backup(backup_id.strip())
        if data is None:
            await interaction.response.send_message(
                f"Backup `{backup_id}` not found. Check /backup list.", ephemeral=True); return
        if confirm != "RESTORE":
            await interaction.response.send_message(
                f"⚠️ **Restore preview — `{path.stem}`**\n"
                f"From: {data.get('guild_name', '?')} (ID {data.get('guild_id')}) at {str(data.get('created_at'))[:19]}\n"
                f"Will create/reuse: {len(data.get('roles', []))} roles, "
                f"{len(data.get('categories', []))} categories, "
                f"{len(data.get('text_channels', []))} text + {len(data.get('voice_channels', []))} voice channels, "
                f"{len(data.get('emojis', []))} emojis, "
                f"{len(data.get('members', []))} member role sets, "
                f"{len(data.get('bans', []))} bans, and "
                f"{sum(len(v) for v in data.get('bot_data', {}).values() if isinstance(v, list))} bot data rows "
                f"(warns, reports, appeals, levels, etc. — keyed by user ID, so a warned user stays warned).\n"
                f"Nothing existing is deleted. To proceed, run again with confirm = `RESTORE`.",
                ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        counts = await restore_snapshot(interaction.guild, data)
        failed = f"\nFailed items: {len(counts['failed'])}" + (
            "\n" + "\n".join(counts["failed"][:10]) if counts["failed"] else "")
        await interaction.followup.send(
            f"✅ **Restore complete from `{path.stem}`**\n"
            f"Roles created: {counts['roles_created']} (reused: {counts['roles_reused']}), "
            f"Categories created: {counts['categories_created']}, "
            f"Channels created: {counts['channels_created']} (reused: {counts['channels_reused']}), "
            f"Emojis created: {counts['emojis_created']}, "
            f"Members re-roled: {counts['members_updated']}, "
            f"Bans restored: {counts['bans_restored']}, "
            f"Bot data rows restored: {counts['bot_rows']}.{failed}",
            ephemeral=True)

    @app_commands.command(name="auto", description="Turn daily auto-backup on or off (staff)")
    @app_commands.choices(state=[app_commands.Choice(name="on", value="on"),
                                 app_commands.Choice(name="off", value="off")])
    async def auto(self, interaction: discord.Interaction, state: app_commands.Choice[str]):
        if not _staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        db.set_setting(interaction.guild.id, "backup_auto", state.value)
        await interaction.response.send_message(
            f"Daily auto-backup is now **{state.value}** for this server. "
            f"When on, a full backup is saved automatically once a day. "
            f"Check them with /backup list.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BackupGroup(bot))
