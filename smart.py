"""Smart layer for NEWR Support — 100% local, free, no API key needed.

This module is deliberately NOT an AI model and never claims to be one.
It is a curated knowledge base + fuzzy matching + rule-based triage:

1. Rotating tips (security, support etiquette, scam/phishing, safety,
   NEWR LABS-specific). ``daily_tip`` is deterministic by calendar day,
   so the whole server sees the same tip on the same day.
2. Fuzzy FAQ matching: token overlap + difflib similarity, so a
   question that does not exactly match a stored topic still finds
   the closest answer, plus related topics.
3. Ticket/report/bug triage: keyword classification into a category,
   a priority, and the staff category that should handle it, using
   the same category names as roles.py (support / moderator / admin).

If an OpenAI-compatible AI key is ever configured for this bot, callers
may optionally use it for a smarter reply — but this module alone never
needs it, never fakes an AI answer, and never claims a paid model ran.
"""
from __future__ import annotations

import re
from datetime import date
from difflib import SequenceMatcher

TIPS: list[dict[str, str]] = [
    # Security
    {"category": "security", "text": "Security tip: turn on 2FA for Discord (Settings > My Account) and never share your password, token, or backup codes — real staff will never ask for them."},
    {"category": "security", "text": "Security tip: check Settings > Authorized Apps regularly and remove apps/bots you no longer use. A stale app keeps access until you revoke it."},
    {"category": "security", "text": "Security tip: use a unique password for Discord, stored in a password manager. Reusing a leaked password from another site is the most common way accounts get taken over."},
    {"category": "security", "text": "Security tip: be suspicious of any DM claiming your account will be deleted, banned, or verified in 24 hours. That urgency is a classic social-engineering trick — verify in the server, not via the DM link."},
    # Scam / phishing
    {"category": "scam", "text": "Scam warning: 'Free Nitro', fake giveaways, and QR-code 'verification' links sent by DM are almost always phishing. Never scan a QR code to log in for someone else, and never paste a token anywhere."},
    {"category": "scam", "text": "Scam warning: if a stranger offers to 'check' your account, gift you something, or asks you to run a script / paste code into Discord, stop — that is how tokens get stolen. Report it with /report instead."},
    {"category": "scam", "text": "Scam warning: check the sender, not just the avatar. Scammers copy staff names and avatars. Real staff help in public ticket channels, not by pressuring you in a secret DM."},
    {"category": "scam", "text": "Scam warning: a link that looks like discord.com but has extra words, misspellings, or a different domain (e.g. disc0rd, discord-gift) is fake. Type discord.com yourself instead of clicking it."},
    # Support etiquette
    {"category": "support", "text": "Support tip: when you open a ticket, say what happened, when it happened, and what you already tried. One clear message gets you help much faster than 'help please' alone."},
    {"category": "support", "text": "Support tip: one issue per ticket, please. Mixing a ban appeal, a bug, and a suggestion in one ticket slows every answer down."},
    {"category": "support", "text": "Support tip: screenshots beat descriptions. For a bug, include a screenshot (with private info blurred) and the exact error text if there is one."},
    {"category": "support", "text": "Support tip: don't ping staff repeatedly in a ticket. Staff see new tickets in order; extra pings don't move you up the queue, they just add noise."},
    {"category": "support", "text": "Support tip: if a staff answer solves your problem, say so and let the ticket close — it keeps the queue clear for the next person."},
    # Server safety
    {"category": "safety", "text": "Server safety tip: new account + no roles + urgent DM = high risk. If a brand-new account DMs you a link or an offer, ignore it and report it with /report."},
    {"category": "safety", "text": "Server safety tip: keep personal info (real name, school, phone, address, face photos) out of public channels. Once posted, it cannot reliably be taken back."},
    {"category": "safety", "text": "Server safety tip: use /verify as soon as you join. Verified roles unlock the real channels and protect the server from raid/bot accounts."},
    {"category": "safety", "text": "Server safety tip: if you see spam, a raid, or many accounts joining at once, don't engage — use /report and let moderators lock down with /lockdown if needed."},
    # NEWR LABS specific
    {"category": "newr", "text": "NEWR LABS tip: use /ticket_create for private help, /faq for common questions, and /roles to see every role on the server and what it can do."},
    {"category": "newr", "text": "NEWR LABS tip: ping roles (GROK Ping, CHATGPT Ping, GEMINI Ping, and friends) are notification roles — they don't give you staff powers, they just subscribe you to updates."},
    {"category": "newr", "text": "NEWR LABS tip: staff DM support is staff/top-roles only. Members should use /ticket_create in the server — that's the fast, tracked route."},
    {"category": "newr", "text": "NEWR LABS tip: for AI help, use the NEWR AI bot — but you must be a member of NEWR LABS first. Its /ask and /chat commands are the AI route; this Support bot is the human-help route."},
    {"category": "newr", "text": "NEWR LABS tip: suggestions and bug reports filed with /suggest and /bug are stored for the team, even if no one replies instantly. Be specific and they are far more likely to be acted on."},
]

CATEGORIES = sorted({t["category"] for t in TIPS})


def daily_tip(on: date | None = None) -> dict[str, str]:
    """The tip for a given day (today by default), deterministic."""
    d = on or date.today()
    return TIPS[d.toordinal() % len(TIPS)]


def tips_by_category(category: str) -> list[dict[str, str]]:
    return [t for t in TIPS if t["category"] == category.lower()]


_STOPWORDS = {
    "how", "do", "does", "did", "what", "why", "when", "where", "who", "which",
    "is", "are", "am", "was", "were", "be", "been", "the", "a", "an", "to", "of",
    "in", "on", "for", "with", "me", "my", "i", "you", "can", "could", "please",
    "help", "get", "getting", "show", "tell", "give", "about", "and", "or", "it",
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _content_tokens(text: str) -> set[str]:
    return _tokens(text) - _STOPWORDS


def _score(query: str, candidate: str) -> float:
    """Fuzzy score 0..1: sequence similarity + exact overlap + fuzzy tokens.

    Fuzzy tokens matter for real questions: 'verified' should match a
    'verify' FAQ, 'logging in' should match 'login', etc. For each query
    token we take its best SequenceMatcher match against candidate tokens.
    Stopwords are ignored so common words don't swamp the real topic.
    """
    q, c = query.lower(), candidate.lower()
    seq = SequenceMatcher(None, q, c).ratio()
    qt, ct = _content_tokens(q), _content_tokens(c)
    if not qt or not ct:
        return 0.4 * seq
    overlap = len(qt & ct) / len(qt)
    fuzzy = sum(max(SequenceMatcher(None, a, b).ratio() for b in ct) for a in qt) / len(qt)
    return 0.4 * seq + 0.3 * overlap + 0.3 * fuzzy


def fuzzy_faq(query: str, faqs: list[dict]) -> tuple[dict | None, float, list[dict]]:
    """Return (best match, score, related matches) for a FAQ query.

    ``faqs`` is a list of dicts/rows with ``topic`` and ``answer``.
    A score >= 0.30 is treated as a usable match; below that the
    caller should say no good match was found (and show the tip).
    """
    scored = []
    for row in faqs:
        topic = row["topic"] if isinstance(row, dict) else row["topic"]
        answer = row["answer"] if isinstance(row, dict) else row["answer"]
        # Topic matters most: a question about verification should match
        # the "verify" topic even if another answer shares common words.
        scored.append((0.7 * _score(query, topic) + 0.3 * _score(query, answer), row))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return None, 0.0, []
    best_score, best = scored[0]
    related = [row for _, row in scored[1:4]]
    return best, best_score, related


# ---- Triage ----
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "scam": ("scam", "penipuan", "phish", "phishing", "nitro gratis", "free nitro",
             "giveaway palsu", "link mencurigakan", "qr", "token", "hacked link",
             "fake nitro", "akun dicuri", "dicuri"),
    "harassment": ("harass", "bully", "bullying", "toxic", "menghina", "hina",
                   "pelecehan", "ancam", "threat", "doxx", "dox", "spam dm"),
    "account": ("login", "log in", "password", "akun", "verify", "verifikasi",
                "2fa", "otp", "email", "cannot log", "tidak bisa login",
                "lupa password", "forgot password", "locked out", "terkunci"),
    "moderation": ("ban", "banned", "mute", "kick", "appeal", "unban",
                   "timeout", "hukuman", "sanksi", "dibanned", "dimute"),
    "technical": ("bug", "error", "crash", "lag", "down", "tidak jalan",
                  "tidak bisa", "rusak", "broken", "channel", "voice", "suara",
                  "bot tidak", "gagal", "failed"),
    "suggestion": ("saran", "usul", "ide", "fitur", "feature", "request",
                   "suggestion", "tambah", "improve", "perbaiki server"),
}

_PRIORITY = {
    "scam": "high", "harassment": "high", "account": "high",
    "moderation": "medium", "technical": "medium", "suggestion": "low",
}
_STAFF_CATEGORY = {
    "scam": "moderator", "harassment": "moderator", "moderation": "moderator",
    "account": "support", "technical": "support", "suggestion": "support",
}
_NEXT_STEPS = {
    "scam": "Do not click the link or reply to the scammer. Save a screenshot and use /report with the user and the message.",
    "harassment": "Do not engage further. Save evidence (screenshots) and use /report so moderators can act.",
    "account": "Do not share your password/token with anyone. Try password reset first, then describe the exact error in the ticket.",
    "moderation": "Use /appeal with a calm explanation of what happened; staff will review it in order.",
    "technical": "Include what you did, the exact error, and a screenshot (private info blurred) in the ticket.",
    "suggestion": "Describe the idea and why it helps the server — specific suggestions get acted on fastest.",
    "general": "Describe what happened, when, and what you already tried, in one clear message.",
}


def classify(text: str) -> dict[str, str]:
    """Classify free text into category / priority / staff / next step."""
    low = text.lower()
    for category, words in _KEYWORDS.items():
        if any(w in low for w in words):
            return {
                "category": category,
                "priority": _PRIORITY[category],
                "staff_category": _STAFF_CATEGORY[category],
                "next_step": _NEXT_STEPS[category],
            }
    return {"category": "general", "priority": "medium",
            "staff_category": "support", "next_step": _NEXT_STEPS["general"]}


def triage_text(text: str) -> str:
    t = classify(text)
    return (f"🧠 Smart triage: category **{t['category']}**, priority **{t['priority']}**, "
            f"route to **{t['staff_category']}** staff.\n{t['next_step']}")
