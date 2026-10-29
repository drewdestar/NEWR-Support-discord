# NEWR LABS role reference (verified read-only, names only)
Source: live role list of server NEWR LABS (Guild ID example in `.env.example`).
Distinct names: 37 (Jockie Music appears twice in the source list).
Runtime rule: the bot fetches `guild.roles` at startup / on guild join and maps
whatever roles exist then. This table is the default name reference only;
no role ID is hardcoded anywhere in the code. A renamed/removed role stops
matching; a new role falls through to the keyword/permission rules in `roles.py`.
`/roles` (audit) lists every live role in the guild by name, position,
member count and mapped category, so in NEWR LABS it lists all 38 rows below
 (two separate Jockie Music roles, if that is how they exist in Discord, will each appear with their own position and member count).
| # | Role (top to bottom) | Mapped category |
|---|----------------------|-----------------|
| 1 | FOUNDER | owner |
| 2 | Appy | bot |
| 3 | QuantumBot | bot |
| 4 | 👑 Founder | owner |
| 5 | NEWR | owner |
| 6 | 🏛️ Executive | admin |
| 7 | ⭐ Admin | admin |
| 8 | 🛡️ Senior Mod | moderator |
| 9 | ⚔️ Moderator | moderator |
| 10 | 🎯 Team Lead | support |
| 11 | 🤝 Helper | support |
| 12 | 🤖 Bots | bot |
| 13 | Server Booster | trusted |
| 14 | 🎨 Creator | trusted |
| 15 | 🎪 Entertainment | member |
| 16 | 💎 VIP Member | trusted |
| 17 | 🌟 Elite Member | trusted |
| 18 | 🎖️ Verified Member | verified |
| 19 | Unfiltered AI Ping | ping |
| 20 | Update Ping | ping |
| 21 | Ticket Tool | bot |
| 22 | Jockie Music | bot |
| 23 | Jockie Music | bot (duplicate row in source list) |
| 24 | YAGPDB.xyz | bot |
| 25 | 👤 Unverified Member | unverified |
| 26 | New Prompt Ping | ping |
| 27 | GROK Ping | ping |
| 28 | CHATGPT Ping | ping |
| 29 | DEEPSEEK Ping | ping |
| 30 | KIMI Ping | ping |
| 31 | GEMINI Ping | ping |
| 32 | Prompt Share Ping | ping |
| 33 | GIVEAWAY Ping | ping |
| 34 | Apollo Bot | bot |
| 35 | Security | moderator |
| 36 | mute | muted |
| 37 | NEWR AI | bot |
| 38 | NEWR Support | bot |

## Tier summary

- owner: FOUNDER, 👑 Founder, NEWR
- admin: 🏛️ Executive, ⭐ Admin
- moderator: 🛡️ Senior Mod, ⚔️ Moderator, Security
- support/staff: 🎯 Team Lead, 🤝 Helper (plus moderator/admin/owner for tickets)
- verified: 🎖️ Verified Member
- unverified: 👤 Unverified Member
- muted: mute
- bot: Appy, QuantumBot, 🤖 Bots, Ticket Tool, Jockie Music, YAGPDB.xyz, Apollo Bot, NEWR AI, NEWR Support, plus any bot-managed/integration role
- ping (notification): every role ending in "Ping" — Unfiltered AI Ping, Update Ping, New Prompt Ping, GROK Ping, CHATGPT Ping, DEEPSEEK Ping, KIMI Ping, GEMINI Ping, Prompt Share Ping, GIVEAWAY Ping — listed by `/pingroles`
- trusted/member: Server Booster, 🎨 Creator, 💎 VIP Member, 🌟 Elite Member (trusted); 🎪 Entertainment (member)
