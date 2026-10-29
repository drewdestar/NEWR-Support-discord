"""Role auto-detection for NEWR Support.

Runtime behaviour (never hardcoded IDs): on guild join / on_ready the bot
fetches ``guild.roles`` live from Discord and maps every role by, in order:
1. An exact-name reference for the verified NEWR LABS roster (names only,
   no IDs) -- see NEWR_LABS_REFERENCE below and roles_reference.md
2. Discord-managed / bot / integration roles, mute roles, and * Ping roles
3. Name keywords (owner, admin, support, moderator, helper, verified,
   unverified, new) and Discord permissions (administrator, manage_guild,
   kick/ban, manage_messages, moderate_members, manage_roles,
   manage_channels)

Categories are stable strings used by tickets, security and /roles.
New categories added for this guild: "unverified" and "ping"
(notification / ping roles, e.g. any role whose name ends in "Ping").
"""
from __future__ import annotations

import discord

CATEGORIES = [
    "owner", "admin", "moderator", "support", "trusted",
    "verified", "unverified", "member", "new", "muted", "bot", "ping",
]

# Verified read-only from the real NEWR LABS server, top to bottom
# (38 entries as listed; "Jockie Music" appears twice in the source list,
# so the distinct names below are 37, plus the duplicate entry = 38 rows).
# This is a NAME reference only. At runtime the bot still fetches
# guild.roles and maps whatever roles actually exist; a role that is
# renamed or removed simply stops matching, and a new role falls through
# to the keyword/permission rules below. No role ID is stored here.
NEWR_LABS_REFERENCE: list[tuple[str, str]] = [
    ("FOUNDER", "owner"),
    ("Appy", "bot"),
    ("QuantumBot", "bot"),
    ("👑 Founder", "owner"),
    ("NEWR", "owner"),
    ("🏛️ Executive", "admin"),
    ("⭐ Admin", "admin"),
    ("🛡️ Senior Mod", "moderator"),
    ("⚔️ Moderator", "moderator"),
    ("🎯 Team Lead", "support"),
    ("🤝 Helper", "support"),
    ("🤖 Bots", "bot"),
    ("Server Booster", "trusted"),
    ("🎨 Creator", "trusted"),
    ("🎪 Entertainment", "member"),
    ("💎 VIP Member", "trusted"),
    ("🌟 Elite Member", "trusted"),
    ("🎖️ Verified Member", "verified"),
    ("Unfiltered AI Ping", "ping"),
    ("Update Ping", "ping"),
    ("Ticket Tool", "bot"),
    ("Jockie Music", "bot"),
    ("YAGPDB.xyz", "bot"),
    ("👤 Unverified Member", "unverified"),
    ("New Prompt Ping", "ping"),
    ("GROK Ping", "ping"),
    ("CHATGPT Ping", "ping"),
    ("DEEPSEEK Ping", "ping"),
    ("KIMI Ping", "ping"),
    ("GEMINI Ping", "ping"),
    ("Prompt Share Ping", "ping"),
    ("GIVEAWAY Ping", "ping"),
    ("Apollo Bot", "bot"),
    ("Security", "moderator"),
    ("mute", "muted"),
    ("NEWR AI", "bot"),
    ("NEWR Support", "bot"),
]
# The source list has 38 rows (Jockie Music listed twice); distinct names:
NEWR_LABS_REFERENCE_NAMES: list[str] = [name for name, _ in NEWR_LABS_REFERENCE]
_NAME_OVERRIDES: dict[str, str] = dict(NEWR_LABS_REFERENCE)

_KEYWORDS = {
    "owner": ("owner", "founder", "pemilik", "pendiri"),
    "admin": ("admin", "administrator"),
    "support": ("support", "helpdesk", "help-desk", "cs", "customer",
                "agent", "ticket", "dukungan", "bantuan"),
    "moderator": ("mod", "moderator", "staff", "pengawas", "security"),
    "trusted": ("trusted", "helper", "vip", "booster", "elite", "senior", "creator"),
    "verified": ("verified", "verif", "terverifikasi"),
    "unverified": ("unverified", "unverif"),
    "new": ("new", "newcomer", "guest", "baru", "belum"),
    "muted": ("muted", "mute", "timeout", "bisukan"),
    "bot": ("bot",),
}


def _has_keyword(name: str, category: str) -> bool:
    low = name.lower()
    return any(k in low for k in _KEYWORDS[category])


def is_ping_role(role: discord.Role) -> bool:
    """A notification role: name ends with 'Ping' (case-insensitive)."""
    return role.name.strip().lower().endswith("ping")


def categorize_role(role: discord.Role, guild: discord.Guild) -> str:
    """Map one live Discord role to a category. Never uses a fixed ID."""
    # 1. Verified NEWR LABS name reference (names only, no IDs).
    if role.name in _NAME_OVERRIDES:
        return _NAME_OVERRIDES[role.name]
    # 2. Ping roles, bot/integration roles, mute roles.
    if is_ping_role(role):
        return "ping"
    if role.is_bot_managed() or role.is_integration() or _has_keyword(role.name, "bot"):
        return "bot"
    if _has_keyword(role.name, "muted"):
        return "muted"
    # The guild owner's own roles, plus owner/founder names, win first.
    if guild.owner is not None and role in guild.owner.roles:
        if role.permissions.administrator or _has_keyword(role.name, "owner"):
            return "owner"
    if _has_keyword(role.name, "owner"):
        return "owner"
    if role.permissions.administrator or _has_keyword(role.name, "admin"):
        return "admin"
    # Support staff before generic moderators: support roles often also
    # hold manage_messages, but they should route tickets, not bans.
    if _has_keyword(role.name, "support"):
        return "support"
    p = role.permissions
    if (p.kick_members or p.ban_members or p.moderate_members
            or p.manage_messages or p.manage_roles or p.manage_channels
            or p.manage_guild or _has_keyword(role.name, "moderator")):
        return "moderator"
    if _has_keyword(role.name, "trusted"):
        return "trusted"
    # Unverified MUST be checked before verified: "unverified" contains
    # the substring "verified".
    if _has_keyword(role.name, "unverified"):
        return "unverified"
    if _has_keyword(role.name, "verified"):
        return "verified"
    if _has_keyword(role.name, "new"):
        return "new"
    if role.name.lower() in ("@everyone", "everyone"):
        return "member"
    return "member"


def map_guild_roles(guild: discord.Guild) -> dict[str, list[discord.Role]]:
    """Return {category: [roles]} for every role currently in the guild."""
    out: dict[str, list[discord.Role]] = {c: [] for c in CATEGORIES}
    for role in guild.roles:
        out[categorize_role(role, guild)].append(role)
    return out


def roles_in_categories(guild: discord.Guild, *categories: str) -> list[discord.Role]:
    mapping = map_guild_roles(guild)
    roles: list[discord.Role] = []
    for cat in categories:
        roles.extend(mapping.get(cat, []))
    return roles


def support_roles(guild: discord.Guild) -> list[discord.Role]:
    return roles_in_categories(guild, "support", "moderator", "admin", "owner")


def staff_roles(guild: discord.Guild) -> list[discord.Role]:
    return roles_in_categories(guild, "support", "moderator", "admin", "owner")


def ping_roles(guild: discord.Guild) -> list[discord.Role]:
    """All notification/ping roles currently in the guild, highest first."""
    return sorted(roles_in_categories(guild, "ping"),
                  key=lambda r: r.position, reverse=True)


def is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    staff_ids = {r.id for r in staff_roles(member.guild)}
    return any(r.id in staff_ids for r in member.roles)


# DM gate for NEWR Support (names only, never role IDs).
# Private-chat support is ONLY for these staff / top roles in NEWR LABS.
# Regular members (Verified Member, VIP, Elite, Creator, etc.) and
# non-members do NOT get DM support; they are directed to /ticket_create
# in the server. The guild owner is also treated as top staff, since
# they outrank every role in the guild.
DM_STAFF_ROLE_NAMES: frozenset[str] = frozenset({
    "FOUNDER",
    "👑 Founder",
    "NEWR",
    "🏛️ Executive",
    "⭐ Admin",
    "🛡️ Senior Mod",
    "⚔️ Moderator",
    "🎯 Team Lead",
    "🤝 Helper",
    "Security",
})


def dm_staff_roles(member: discord.Member) -> list[discord.Role]:
    """Staff/top roles held by a member, matched by name at runtime."""
    return [r for r in member.roles if r.name in DM_STAFF_ROLE_NAMES]


def is_dm_staff(member: discord.Member) -> bool:
    """True only for staff/top roles in the DM gate, or the guild owner."""
    if member.guild is not None and member.guild.owner_id == member.id:
        return True
    return bool(dm_staff_roles(member))


def highest_category(member: discord.Member) -> str:
    """Highest-priority category held by a member, by category order."""
    held = {categorize_role(r, member.guild) for r in member.roles}
    for cat in CATEGORIES:
        if cat in held:
            return cat
    return "member"
