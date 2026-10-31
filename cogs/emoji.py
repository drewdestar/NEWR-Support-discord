"""NEWR LABS custom emojis — the Nitro-style set.

These are APPLICATION emojis owned by the NEWR Support bot
itself (not guild/server emojis, not Unicode). They live on
the application, so no emoji is stored in NEWR LABS. Artwork:
Lucide icons (MIT) rendered at 4096x4096, black stroke
with a THINNER white outline (3.0 vs 2, user-approved)
on transparent background — black and white only, no
badge. IDs verified from Discord after upload; sources
are /tmp/lucide (Lucide SVGs) rendered by cairosvg to
/tmp/thinner_final. (Filled Font Awesome iOS-like
preview was rejected by the user; not used, except
newr_handshake and newr_settings, which the user
chose to keep in the filled version. The 45-emoji
expansion (2026-10-31) added Lucide icons plus
those two FA icons; newr_shield stays the iOS
filled version.)

Use str() for embed text, or partial() for button/select emoji
fields, which need a PartialEmoji, not a string.
"""
from __future__ import annotations

import discord

IDS = {
    "newr_apply": "1565944112891564132",
    "newr_ban": "1565944124090351636",
    "newr_bug": "1565944135314178138",
    "newr_chat": "1565944146638934096",
    "newr_check": "1565944158147969226",
    "newr_clock": "1565944169711665255",
    "newr_cross": "1565944181921415238",
    "newr_info": "1565944193954877541",
    "newr_lock": "1565944206298451968",
    "newr_mute": "1565944220592898179",
    "newr_party": "1565944232886403173",
    "newr_role": "1565944244651429938",
    "newr_shield": "1565946125838581951",
    "newr_star": "1565944267577237634",
    "newr_ticket": "1565944279514349679",
    "newr_trash": "1565944291463798834",
    "newr_user": "1565944312880177332",
    "newr_warn": "1565944324863295528",
    "newr_book": "1565949882848514140",
    "newr_boot": "1565949894798090270",
    "newr_bot": "1565949907595042816",
    "newr_briefcase": "1565949920609959997",
    "newr_bulb": "1565949942403436544",
    "newr_cake": "1565949954885681204",
    "newr_calendar": "1565949967292436581",
    "newr_chart": "1565949979627884695",
    "newr_crown": "1565949991216746637",
    "newr_doc": "1565950003762176040",
    "newr_door": "1565950016994938920",
    "newr_hammer": "1565950028457975888",
    "newr_hand": "1565950039497637988",
    "newr_handshake": "1565950050977447966",
    "newr_heart": "1565950062213734450",
    "newr_high": "1565950075438375013",
    "newr_id": "1565950087371292732",
    "newr_image": "1565950099497160755",
    "newr_landmark": "1565950112562155591",
    "newr_link": "1565950124444876801",
    "newr_low": "1565950136830529566",
    "newr_mail": "1565950149916631130",
    "newr_megaphone": "1565950161971056701",
    "newr_mid": "1565950174176743556",
    "newr_noentry": "1565950186151354388",
    "newr_package": "1565950197828292719",
    "newr_palette": "1565950209979056249",
    "newr_pencil": "1565950222973272064",
    "newr_pin": "1565950235308589126",
    "newr_ping": "1565950248323387402",
    "newr_plus": "1565950261162283038",
    "newr_pushpin": "1565950273837604894",
    "newr_repeat": "1565950286114324583",
    "newr_scale": "1565950298055385219",
    "newr_scroll": "1565950310763987056",
    "newr_settings": "1565950322331885630",
    "newr_signal": "1565950334365601823",
    "newr_sword": "1565950346139013302",
    "newr_tag": "1565950358109552640",
    "newr_target": "1565950369383587860",
    "newr_unlock": "1565950381362520064",
    "newr_urgent": "1565950393127796806",
    "newr_users": "1565950405177770014",
    "newr_volume": "1565950417211498657",
    "newr_wrench": "1565950429643276369",
}

ANIMATED = set()


def str_emoji(name: str) -> str:
    prefix = "a" if name in ANIMATED else ""
    return f"<{prefix}:{name}:{IDS[name]}>"


def partial(name: str) -> discord.PartialEmoji:
    return discord.PartialEmoji(name=name, id=int(IDS[name]),
                                animated=name in ANIMATED)


# Unicode -> custom, applied centrally in cogs.ui.panel/make so every
# embed the bot sends uses the custom set instead of stock emojis.
# Only emojis the bot itself puts in titles/fields are mapped; user
# text is never touched (translation happens on bot-built strings
# before they reach Discord, and only for these exact tokens).
MAP = {
    "✅": str_emoji("newr_check"),
    "❌": str_emoji("newr_cross"),
    "⚠️": str_emoji("newr_warn"),
    "ℹ️": str_emoji("newr_info"),
    "🔒": str_emoji("newr_lock"),
    "🎟️": str_emoji("newr_ticket"),
    "🎫": str_emoji("newr_ticket"),
    "📝": str_emoji("newr_apply"),
    "🛡️": str_emoji("newr_shield"),
    "🔨": str_emoji("newr_ban"),
    "🔇": str_emoji("newr_mute"),
    "⭐": str_emoji("newr_star"),
    "🧹": str_emoji("newr_trash"),
    "⏱️": str_emoji("newr_clock"),
    "👤": str_emoji("newr_user"),
    "🎖️": str_emoji("newr_role"),
    "💬": str_emoji("newr_chat"),
    "🎉": str_emoji("newr_party"),
    "🐛": str_emoji("newr_bug"),
    "📄": str_emoji("newr_doc"),
    "📅": str_emoji("newr_calendar"),
    "💡": str_emoji("newr_bulb"),
    "🔓": str_emoji("newr_unlock"),
    "✏️": str_emoji("newr_pencil"),
    "➕": str_emoji("newr_plus"),
    "➖": str_emoji("newr_mid"),
    "🔊": str_emoji("newr_volume"),
    "🎯": str_emoji("newr_target"),
    "👥": str_emoji("newr_users"),
    "🤖": str_emoji("newr_bot"),
    "👑": str_emoji("newr_crown"),
    "🤝": str_emoji("newr_handshake"),
    "📩": str_emoji("newr_mail"),
    "🔗": str_emoji("newr_link"),
    "📌": str_emoji("newr_pushpin"),
    "⚖️": str_emoji("newr_scale"),
    "🛠️": str_emoji("newr_wrench"),
    "🎂": str_emoji("newr_cake"),
    "🎨": str_emoji("newr_palette"),
    "📣": str_emoji("newr_megaphone"),
    "🖼️": str_emoji("newr_image"),
    "📖": str_emoji("newr_book"),
    "🔁": str_emoji("newr_repeat"),
    "📜": str_emoji("newr_scroll"),
    "⚙️": str_emoji("newr_settings"),
    "🚪": str_emoji("newr_door"),
    "🚫": str_emoji("newr_noentry"),
    "📦": str_emoji("newr_package"),
    "💼": str_emoji("newr_briefcase"),
    "🏛️": str_emoji("newr_landmark"),
    "👢": str_emoji("newr_boot"),
    "🏷️": str_emoji("newr_tag"),
    "🆔": str_emoji("newr_id"),
    "📍": str_emoji("newr_pin"),
    "📊": str_emoji("newr_chart"),
    "👋": str_emoji("newr_hand"),
    "⚔️": str_emoji("newr_sword"),
    "🏓": str_emoji("newr_ping"),
    "📶": str_emoji("newr_signal"),
    "❤️": str_emoji("newr_heart"),
}


def translate(text: str) -> str:
    if not text:
        return text
    for uni, custom in MAP.items():
        text = text.replace(uni, custom)
    return text
