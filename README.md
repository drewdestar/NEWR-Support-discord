# NEWR Support — Discord Support + Security Bot

A real, working Discord bot in Python (discord.py, slash commands only,
no prefix commands) for the NEWR LABS server. It is already placed in
the server, so this project does **not** re-invite it: the task is to
make it live and working with a large, useful support + security
command set.

## What it does

- **Tickets:** `/ticket_create`, `/ticket_panel`, `/ticket_claim`,
  `/ticket_close`, `/ticket_transcript`, `/ticket_add`, `/ticket_remove`,
  priority, notes, escalation, queue and status.
- **FAQ / helpdesk:** `/faq`, `/faq_add`, `/faq_list`, `/helpdesk`,
  `/staff_ping`, reports, suggestions, bugs, appeals, feedback.
- **Security:** `/verify` (button), `/captcha_verify`, `/verify_user`,
  account-age and join checks, anti-spam / anti-link / anti-invite /
  anti-raid toggles, lockdown and unlock (channel and server),
  slowmode, quarantine, watchlist, banned words, trusted roles.
- **Moderation:** warn / warns / clear, mute / timeout, kick, ban /
  unban / ban list, purge, nicknames, role add/remove, voice kick/mute.
- **Utility / info:** `/serverinfo`, `/userinfo`, `/roleinfo`,
  `/roles` (full role audit), `/rolecheck`, `/pingroles`,
  `/server_stats`, `/staff_list`, `/command_list`, and more.
- **Total: 100 slash commands** — exactly at Discord's 100-command per-guild limit, so guild sync succeeds (113 were drafted, 14 duplicates were cut after the dry-run hit the tree limit, then `/dm-access` was added as command 100) (see `python3 dry_run.py` output).

## DM (private chat) gate — staff / top roles only

- **Who may DM the bot for support:** staff and top roles in NEWR LABS only —
  FOUNDER, 👑 Founder, NEWR, 🏛️ Executive, ⭐ Admin, 🛡️ Senior Mod,
  ⚔️ Moderator, 🎯 Team Lead, 🤝 Helper, Security (plus the guild owner).
  The check is a runtime lookup by role **name** in NEWR LABS
  (`roles.py`: `DM_STAFF_ROLE_NAMES` / `is_dm_staff`); no role ID is hardcoded.
  Staff DMs get a staff menu (`menu` in DM) and any other DM text is stored
  as a DM support request in SQLite (`dm_requests`) and forwarded to
  `LOG_CHANNEL_ID` when set.
- **Who may NOT DM for support:** regular members (Verified Member, VIP,
  Elite, Creator, etc.) and non-members. They get one polite denial per
  burst (10-minute cooldown, so the bot cannot be spammed into replying),
  directing them to `/ticket_create` in the NEWR LABS server, and their
  message is **not** stored as a support request.
- **Honest Discord limitation:** guild-synced slash commands only appear
  inside the server, so DM support works via direct messages (`on_message`
  in `cogs/dm.py`), **not** via slash commands in a DM. `/dm-access` is a
  guild slash command: run it in the server to check whether you have
  staff DM access, which staff roles matched, or that you are member-only.

## Role auto-detection (no hardcoded role IDs)

On startup and on guild join the bot fetches `guild.roles` live and
maps each role by name keywords and Discord permissions into:
owner, admin, moderator, support, trusted, verified, unverified,
member, new, muted, bot, and ping (notification roles).

The verified NEWR LABS roster is documented by name only in
[`roles_reference.md`](roles_reference.md) (38 rows, top to bottom,
including the duplicated Jockie Music entry in the source list).
Key mappings: FOUNDER / 👑 Founder / NEWR = owner; 🏛️ Executive /
⭐ Admin = admin; 🛡️ Senior Mod / ⚔️ Moderator = moderator;
🎯 Team Lead / 🤝 Helper = support; 🎖️ Verified Member = verified;
👤 Unverified Member = unverified; mute = muted; Bots / NEWR AI /
NEWR Support and other bot/integration roles = bot; every `* Ping`
role = ping (see `/pingroles`).

`/roles` lists **every** live role in the guild — name, position,
member count, and mapped category — so in NEWR LABS it lists all
38 roles. `/rolecheck @member` checks one member against the mapping.


## Smart layer (free, local — no AI key needed)

New in `smart.py`, with no new slash command (total stays at 100):

- **Rotating tips:** `/help` and `/helpdesk` now show a tip of the day, rotating by calendar day across security, scam/phishing, support etiquette, server safety, and NEWR LABS tips. Staff can also type `tip` in a DM to the bot for today's tip.
- **Smart FAQ matching:** `/faq` no longer needs an exact topic. It fuzzy-matches (topic-weighted, stopwords ignored, so "how do I get verified?" finds the `verify` FAQ) and, on a close match, shows the closest answer plus related topics. Below a 0.30 match it says so honestly and shows the tip of the day instead of guessing.
- **Smart ticket triage:** `/ticket_create`, `/report`, `/bug`, `/suggest`, `/appeal`, and `/staff_ping` now classify the text locally into account / scam / harassment / moderation / technical / suggestion / general, with a priority (high/medium/low) and the staff category that should handle it (support vs moderator, using the roles.py mapping). The triage is posted in the ticket and in the confirmation — it is a rule-based suggestion, not an AI verdict.
- **Optional AI:** if an OpenAI-compatible AI key is ever configured for this bot in future, it may be used for smarter replies, but the local layer above works with no key and never fakes an AI answer or claims a paid model ran.

## Setup

1. Python 3.11+ and a Discord application with a bot user.
   The bot is already in NEWR LABS; do not invite it again unless
   you are setting up a fresh copy.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and fill it in:

   ```bash
   cp .env.example .env
   ```

   - `DISCORD_TOKEN` — bot token from the Developer Portal.
     **Never commit `.env`, never paste a token into code, chat, or
     this README.** If a token leaks, reset it in the portal.
   - `GUILD_ID` — guild to sync slash commands to. The example
     value in `.env.example` is NEWR LABS
     (`1465422166790242377`); the code reads it from the
     environment and does not hardcode it.
   - `LOG_CHANNEL_ID`, `SUPPORT_CATEGORY_ID` — optional.

4. Invite scopes (only for a fresh copy): `bot` +
   `applications.commands`.
   Required intents in the Developer Portal (Bot section):
   **Server Members Intent** and **Message Content Intent**
   (needed for member joins, role checks, and anti-spam/link).
   The bot also needs, in the server: Manage Channels, Manage Roles
   (above the roles it assigns), Kick/Ban Members, Moderate Members
   (timeouts), Manage Messages, Read Message History, Send Messages.

5. Run:

   ```bash
   python3 bot.py
   ```

   On ready it prints the live role mapping and syncs the slash
   commands to `GUILD_ID`. Slash commands may take a few minutes
   to appear in Discord the first time.

## Self-test (no token, no Discord connection)

```bash
python3 -m py_compile bot.py roles.py db.py dry_run.py cogs/*.py
python3 dry_run.py
```

`dry_run.py` loads every cog, counts slash commands from the
command tree, and asserts 99-100 (the Discord guild cap). It never connects to Discord
and never needs a token.

## Data

Tickets, warnings, settings, reports, suggestions, bugs, appeals,
feedback, watchlists, banned words, and FAQs are stored in a local
SQLite file (`data.db` by default, or `DB_PATH` if set). No token,
secret, or password is stored in code, in the database, or in docs.

## Shared brain (one brain, two bots)

Both bots read and write the SAME SQLite file:
`~/workspace/bots/shared-brain/memory.db` (or `SHARED_BRAIN_DB` in
`.env`, which must be the same path for both bots). What Support
learns (tickets, reports, bugs, appeals) is visible to AI via
`recall_cross_bot`, and what AI learns (chats, preferences) is
visible to Support. The bots also talk to each other through the
`bot_messages` queue in that database: Support sends `ticket_update`
messages to AI, AI sends `ai_summary` messages to Support when a
user asks for staff/ticket help. Each bot polls its own inbox every
45 seconds, handles each message once, and marks it done in a
finally block; a bot never replies to a bot_message with a new
bot_message of the same kind, so the two bots cannot loop forever.
No passwords, tokens, or API keys are ever stored in the brain, and
`forget_user` deletes a user's rows across both bots.
