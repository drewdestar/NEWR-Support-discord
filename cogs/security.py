"""Security cog: verification, anti-spam/link/raid, lockdown, quarantine."""
from __future__ import annotations

import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import discord
from cogs.emoji import partial
from cogs.ui import denied as _denied
from discord import app_commands
from discord.ext import commands

import db
from roles import categorize_role, is_staff, map_guild_roles

EMBED_COLOR = 0xED4245


def emb(title: str, desc: str) -> discord.Embed:
    from cogs.ui import panel
    return panel(title, desc, EMBED_COLOR)


def staff_only(i: discord.Interaction) -> bool:
    return is_staff(i.user)  # type: ignore[arg-type]


async def _verify_member(guild: discord.Guild, member: discord.Member, via: str) -> bool:
    """Shared verify step for button / math / image / hidden-word.

    Adds Verified, removes Unverified, and logs the success to
    #logs (Verifeon-style verification logs), so staff can see
    who verified and how, instead of verifications being silent.
    """
    verified = [r for r in guild.roles if categorize_role(r, guild) == "verified"]
    if not verified:
        return False
    try:
        await member.add_roles(*verified, reason=f"Verification ({via})")
    except discord.HTTPException:
        return False
    unverified = [r for r in guild.roles if categorize_role(r, guild) == "unverified"]
    if unverified:
        try:
            await member.remove_roles(*unverified, reason=f"Verification ({via})")
        except discord.HTTPException:
            pass
    try:
        from cogs.modlog import log_action
        await log_action(guild, "Verified", member, None, "Verification completed",
                         extra=f"Via: {via}")
    except Exception:
        pass
    return True


def _new_verify_code() -> str:
    """A fresh image-captcha code, letters + digits, never just a number.

    Alphabet excludes ambiguous 0/1/I/O. With 32 characters x 5
    positions there are 33 million combinations, so the answer is
    effectively never the same twice — unlike the old math captcha,
    whose answer could only be 4-18 and could repeat by chance.
    """
    import random as _random
    import string as _string
    alphabet = "".join(c for c in _string.ascii_uppercase + _string.digits if c not in "01IO")
    return "".join(_random.choice(alphabet) for _ in range(5))


class VerifyImageModal(discord.ui.Modal, title="Human Check"):
    """Answer box for the image captcha: code is checked against
    the verify_captchas DB row, never encoded in a custom_id, so
    the answer cannot be read off the button/modal itself.
    """
    def __init__(self) -> None:
        super().__init__(title="Human Check")
        self.answer_input = discord.ui.TextInput(
            label="Type the code from the image", placeholder="e.g. K7XQ2",
            max_length=10)
        self.add_item(self.answer_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from cogs.ui import err, ok as ok_embed, panel
        from roles import categorize_role
        # Already verified beats "expired": after a correct answer the
        # row is deleted, so a second (stale) modal submit must not
        # report "Captcha Expired" to an already-verified user.
        verified = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "verified"]  # type: ignore[attr-defined]
        if verified and any(r in interaction.user.roles for r in verified):  # type: ignore[attr-defined]
            await interaction.response.send_message(
                embed=panel("✅ Already Verified", "You already have the Verified role — no captcha needed."),
                ephemeral=True); return
        with db._conn() as conn:
            row = conn.execute("SELECT code FROM verify_captchas WHERE user_id=? AND guild_id=?",
                               (interaction.user.id, interaction.guild.id)).fetchone()
        if row is None:
            await interaction.response.send_message(
                embed=err("Captcha Expired", "Click Verify again for a new image."), ephemeral=True); return
        if str(self.answer_input).strip().upper() == row["code"].upper():
            with db._conn() as conn:
                conn.execute("DELETE FROM verify_captchas WHERE user_id=? AND guild_id=?",
                             (interaction.user.id, interaction.guild.id))
            ok = await _verify_member(interaction.guild, interaction.user, "captcha (image verify)")  # type: ignore[arg-type]
            if not ok:
                await interaction.response.send_message(embed=err("Verification Failed", "No verified role found on this server."), ephemeral=True); return
            await interaction.response.send_message(embed=ok_embed("Verified!", "✅ Correct! You now have the Verified role and can access the server."), ephemeral=True)
        else:
            # Row is NOT deleted on a wrong answer: the same captcha
            # stays active, so the user retries the same image
            # (via Enter Answer) instead of spamming Verify for a
            # new, easier code.
            await interaction.response.send_message(embed=err("Wrong Answer", "That code was wrong. Your current captcha is still active — try again with the same image (Enter Answer). Tip: if the modal hides the image on your phone, close it and use 'Answer in DM' on the captcha message instead — the image stays visible in your DM chat while you type. No role was given."), ephemeral=True)


class VerifyAnswerView(discord.ui.View):
    """Ephemeral answer buttons attached to the captcha image message.

    Discord modals cannot contain an image, so on mobile the modal
    covers the captcha image while the user types — they have to
    remember the code. 'Answer in DM' is the workaround: the bot
    DMs the same image, and in a DM chat the image stays visible
    above the keyboard while the user types their reply.
    """
    def __init__(self) -> None:
        super().__init__(timeout=600)

    @discord.ui.button(label="Enter Answer", style=discord.ButtonStyle.primary)
    async def answer(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        await interaction.response.send_modal(VerifyImageModal())

    @discord.ui.button(label="Answer in DM", style=discord.ButtonStyle.secondary)
    async def answer_dm(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        import io as _io
        from cogs.ui import err, panel
        with db._conn() as conn:
            row = conn.execute("SELECT code, created_at FROM verify_captchas WHERE user_id=? AND guild_id=?",
                               (interaction.user.id, interaction.guild.id)).fetchone()
        if row is None:
            await interaction.response.send_message(
                embed=err("Captcha Expired", "Click Verify again for a new image."), ephemeral=True); return
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))).total_seconds()
        except Exception:
            age = 999999
        if age >= 600:
            with db._conn() as conn:
                conn.execute("DELETE FROM verify_captchas WHERE user_id=? AND guild_id=?",
                             (interaction.user.id, interaction.guild.id))
            await interaction.response.send_message(
                embed=err("Captcha Expired", "Click Verify again for a new image."), ephemeral=True); return
        try:
            dm_msg = await interaction.user.send(
                embed=panel("🔒 Human Check", "Reply to this DM with the code from the image below. You can see the image above while you type. If your answer is wrong, this message is automatically deleted and a fresh copy of the same captcha is sent."),
                file=discord.File(_io.BytesIO(_make_captcha_image(row["code"])), filename="captcha.png"))
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=err("DMs Closed", "I could not DM you — your DMs are closed. Use 'Enter Answer' (modal) instead."), ephemeral=True); return
        with db._conn() as conn:
            conn.execute("UPDATE verify_captchas SET dm_message_id=? WHERE user_id=? AND guild_id=?",
                         (dm_msg.id, interaction.user.id, interaction.guild.id))
        await interaction.response.send_message(
            embed=panel("📩 Check Your DM", "I sent the same captcha image to your DM. Reply there with the code — the image stays visible while you type."),
            ephemeral=True)


class VerifyView(discord.ui.View):
    """THE verification panel: one button, one image captcha, no bypass.

    Clicking Verify never grants Verified directly. It generates a
    One image captcha at a time (letters + digits, rendered as a
    picture, not a math question), sends it as an ephemeral message
    in-server (no DM needed, so closed DMs cannot block it), and
    only a correct typed answer calls _verify_member. There is no
    separate verify panel and no separate captcha panel: verify IS
    the captcha, in a single flow.
    """
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, emoji=partial("newr_lock"), custom_id="newr_support_verify")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):  # noqa: ARG002
        import io as _io
        from cogs.ui import err, panel
        from roles import categorize_role
        member = interaction.user  # type: ignore[attr-defined]
        verified = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "verified"]  # type: ignore[attr-defined]
        if verified and any(r in member.roles for r in verified):
            await interaction.response.send_message(
                embed=panel("✅ Already Verified", "You already have the Verified role — no captcha needed."),
                ephemeral=True); return
        # Anti-spam: only ONE captcha message per active captcha.
        # If they already have one (unanswered, less than 10
        # minutes old), this click is silently acknowledged and
        # NOTHING new is sent at all. After 10 minutes the old
        # one is expired and a new one is allowed, so a user is
        # never stuck forever on a lost/expired image.
        with db._conn() as conn:
            existing = conn.execute("SELECT code, created_at FROM verify_captchas WHERE user_id=? AND guild_id=?",
                                    (member.id, interaction.guild.id)).fetchone()
        if existing is not None:
            try:
                from datetime import datetime as _dt
                age = (_dt.now(timezone.utc) - _dt.fromisoformat(existing["created_at"].replace("Z", "+00:00"))).total_seconds()
            except Exception:
                age = 999999
            if age < 600:
                # Only ONE captcha message, ever, per active captcha:
                # silently acknowledge this click and send NOTHING
                # new. Resending the same image still stacks a new
                # ephemeral message on every click, which is exactly
                # the spam in the user's screenshot. The user already
                # has the one active message to answer.
                await interaction.response.defer_update()
                return
            else:
                with db._conn() as conn:
                    conn.execute("DELETE FROM verify_captchas WHERE user_id=? AND guild_id=?",
                                 (member.id, interaction.guild.id))
                code = _new_verify_code()
                with db._conn() as conn:
                    conn.execute("INSERT INTO verify_captchas VALUES (?, ?, ?, ?)",
                                 (member.id, interaction.guild.id, code, db.now()))
        else:
            code = _new_verify_code()
            with db._conn() as conn:
                conn.execute("INSERT INTO verify_captchas VALUES (?, ?, ?, ?)",
                             (member.id, interaction.guild.id, code, db.now()))
        try:
            await interaction.response.send_message(
                embed=panel("🔒 Human Check", "Type the code shown in the image below, then click Enter Answer. You can only have one active captcha at a time — clicking Verify again while this one is active will not send another message, so answer this one. On a phone the modal can hide this image while you type: use 'Answer in DM' below instead and the image stays visible in your DM chat while you type."),
                file=discord.File(_io.BytesIO(_make_captcha_image(code)), filename="captcha.png"),
                view=VerifyAnswerView(), ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=err("Verification Failed", "Could not send the captcha image. Click Verify again."),
                ephemeral=True)


class CaptchaModal(discord.ui.Modal):
    """Math captcha, stateless: the question is encoded in custom_id.

    BetterAntispam-style modes are button / image CAPTCHA / math /
    hidden word. A math modal is the one that works fully inside
    Discord without an image server: a=7, b=5 -> custom_id
    "newr_captcha_7_5", and on_submit parses it back. No state is
    stored, so a restart between button and answer cannot break it
    (the modal itself is held by Discord, not by the bot).
    """
    def __init__(self, a: int, b: int) -> None:
        super().__init__(title="Human Check", custom_id=f"newr_captcha_{a}_{b}")
        self.answer_input = discord.ui.TextInput(
            label=f"What is {a} + {b}?", placeholder="Type the number",
            max_length=10)
        self.add_item(self.answer_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        from cogs.ui import err, ok as ok_embed
        try:
            _, _, a, b = self.custom_id.split("_")
            correct = int(a) + int(b)
        except Exception:
            await interaction.response.send_message(embed=err("Captcha Expired", "Please click Verify again for a new question."), ephemeral=True); return
        if str(self.answer_input).strip() == str(correct):
            ok = await _verify_member(interaction.guild, interaction.user, "captcha (verify)")  # type: ignore[arg-type]
            if not ok:
                await interaction.response.send_message(embed=err("Verification Failed", "No verified role found on this server."), ephemeral=True); return
            await interaction.response.send_message(embed=ok_embed("Verified!", "✅ Correct! You now have the Verified role and can access the server."), ephemeral=True)
        else:
            await interaction.response.send_message(embed=err("Wrong Answer", "That answer was wrong. Click Verify again to try a new question — no role was given."), ephemeral=True)


def _make_captcha_image(code: str) -> bytes:
    """Render a captcha image with PIL (BetterAntispam image mode).

    White background, black bold letters with slight rotation and
    noise lines/dots, so it is readable by a human but not by a
    simple text scraper. Generated locally on the VM, no image
    server or paid API needed.
    """
    import io as _io
    import random as _random
    from PIL import Image, ImageDraw, ImageFont
    width, height = 240, 90
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
    except Exception:
        font = ImageFont.load_default()
    x = 15
    for ch in code:
        char_img = Image.new("RGBA", (50, 60), (255, 255, 255, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_draw.text((5, 5), ch, fill=(0, 0, 0), font=font)
        char_img = char_img.rotate(_random.randint(-18, 18), expand=True)
        img.paste(char_img, (x, 15), char_img)
        x += 42
    for _ in range(6):
        draw.line([( _random.randint(0, width), _random.randint(0, height)),
                   (_random.randint(0, width), _random.randint(0, height))],
                  fill=(180, 180, 180), width=1)
    for _ in range(80):
        draw.point((_random.randint(0, width), _random.randint(0, height)), fill=(160, 160, 160))
    buf = _io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()



class Security(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._msg_times: dict[int, list[float]] = defaultdict(list)

    async def _record_violation(self, guild: discord.Guild, author: discord.Member, kind: str) -> None:
        """YAGPDB-style scaling punishments for automod deletions.

        Every automod deletion counts as one violation. In a rolling
        24h window: 3 violations -> 30-minute timeout, 5+ -> 24-hour
        timeout, each logged to #logs via modlog. Staff are never
        counted (on_message returns early for them). Timeouts are
        used instead of kicks: a kick would remove a member for
        spam, which is harsher than YAGPDB's default ladder needs
        to be here, and a timeout is reversible by staff.
        """
        try:
            with db._conn() as conn:
                conn.execute("INSERT INTO automod_violations VALUES (NULL, ?, ?, ?, ?)",
                             (guild.id, author.id, kind, db.now()))
                cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
                count = conn.execute(
                    "SELECT COUNT(*) FROM automod_violations WHERE guild_id=? AND user_id=? AND created_at>=?",
                    (guild.id, author.id, cutoff)).fetchone()[0]
            minutes = 0
            if count >= 5:
                minutes = 1440
            elif count >= 3:
                minutes = 30
            if minutes:
                try:
                    await author.timeout(timedelta(minutes=minutes), reason=f"Automod: {count} violations in 24h ({kind})")
                except discord.HTTPException:
                    return
                from cogs.modlog import log_action
                await log_action(guild, "Muted", author, None, "Automod scaling punishment",
                                 extra=f"Duration: {minutes} minutes (automod, {count} violations in 24h)")
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild:
            # DM reply to a VERIFY captcha sent via 'Answer in DM':
            # only active when dm_message_id is set (user actually
            # chose the DM path). Unlike the ephemeral in-server
            # message, a real DM message CAN be deleted by the bot,
            # so a wrong answer auto-deletes the old captcha
            # message and sends a fresh copy of the SAME code.
            # If the reply matches a captcha-on-join code instead,
            # fall through to the image_captchas handler below.
            with db._conn() as conn:
                vrow = conn.execute(
                    "SELECT guild_id, code, created_at, dm_message_id FROM verify_captchas WHERE user_id=? AND dm_message_id IS NOT NULL",
                    (message.author.id,)).fetchone()
            if vrow is not None:
                # Join-captcha match takes precedence: fall through.
                with db._conn() as conn:
                    irow = conn.execute(
                        "SELECT code FROM image_captchas WHERE user_id=? LIMIT 1",
                        (message.author.id,)).fetchone()
                    in_app = conn.execute(
                        "SELECT 1 FROM dm_applications WHERE user_id=? LIMIT 1",
                        (message.author.id,)).fetchone() is not None
                content = message.content.strip().upper()
                if irow is not None and content == irow["code"].upper() and content != vrow["code"].upper():
                    pass  # join captcha: fall through to handler below
                elif in_app and content != vrow["code"].upper():
                    return  # DM application answer, not a captcha attempt
                else:
                    async def _delete_dm_captcha() -> None:
                        if vrow["dm_message_id"]:
                            try:
                                old = await message.channel.fetch_message(vrow["dm_message_id"])
                                await old.delete()
                            except Exception:
                                pass
                    try:
                        vcreated = datetime.fromisoformat(vrow["created_at"])
                        if vcreated.tzinfo is None:
                            vcreated = vcreated.replace(tzinfo=timezone.utc)
                        vexpired = (datetime.now(timezone.utc) - vcreated) > timedelta(minutes=10)
                    except Exception:
                        vexpired = True
                    if vexpired:
                        await _delete_dm_captcha()
                        with db._conn() as conn:
                            conn.execute("DELETE FROM verify_captchas WHERE user_id=?", (message.author.id,))
                        await message.channel.send("That captcha expired (10 minutes). Please click Verify in #verification again.")
                        return
                    if content == vrow["code"].upper():
                        await _delete_dm_captcha()
                        with db._conn() as conn:
                            conn.execute("DELETE FROM verify_captchas WHERE user_id=?", (message.author.id,))
                        vguild = self.bot.get_guild(vrow["guild_id"])
                        if vguild is None:
                            await message.channel.send("Server not found. Please try again in the server."); return
                        vmember = vguild.get_member(message.author.id)
                        if vmember is None:
                            await message.channel.send("You are not in the server anymore."); return
                        vok = await _verify_member(vguild, vmember, "captcha (image verify, DM answer)")
                        await message.channel.send("✅ Correct! You are verified!" if vok else "No verified role found on this server.")
                        return
                    # Wrong: auto-delete the old DM captcha message,
                    # then resend the SAME code as a fresh DM message
                    # (no code refresh, so wrong answers cannot be
                    # used to fish for an easier code).
                    await _delete_dm_captcha()
                    import io as _io2
                    from cogs.ui import panel as _panel
                    try:
                        new_dm = await message.channel.send(
                            embed=_panel("🔒 Human Check", "❌ Wrong code. The old captcha message was deleted. Reply to this DM with the code from the image below — you can see it above while you type."),
                            file=discord.File(_io2.BytesIO(_make_captcha_image(vrow["code"])), filename="captcha.png"))
                        with db._conn() as conn:
                            conn.execute("UPDATE verify_captchas SET dm_message_id=? WHERE user_id=? AND guild_id=?",
                                         (new_dm.id, message.author.id, vrow["guild_id"]))
                    except Exception:
                        await message.channel.send("❌ Wrong code. Click Verify in #verification to try again.")
                    return
            # DM reply to an image captcha: check the code, verify
            # in the stored guild, expire after 10 minutes.
            with db._conn() as conn:
                rows = conn.execute(
                    "SELECT guild_id, code, created_at FROM image_captchas WHERE user_id=?",
                    (message.author.id,)).fetchall()
            if not rows:
                return
            # Same ownership rule as the DM gate: a DM application
            # owns the DM while in progress, so an application answer
            # must not be counted as a wrong captcha attempt. Only an
            # exact captcha code still goes through here.
            with db._conn() as conn:
                in_application = conn.execute(
                    "SELECT 1 FROM dm_applications WHERE user_id=? LIMIT 1",
                    (message.author.id,)).fetchone() is not None
            if in_application and message.content.strip().upper() != rows[0]["code"].upper():
                return
            try:
                created = datetime.fromisoformat(rows[0]["created_at"])
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                expired = (datetime.now(timezone.utc) - created) > timedelta(minutes=10)
            except Exception:
                expired = True
            if expired:
                with db._conn() as conn:
                    conn.execute("DELETE FROM image_captchas WHERE user_id=?", (message.author.id,))
                await message.channel.send("That captcha expired (10 minutes). Please click Verify in #verification again.")
                return
            if message.content.strip().upper() == rows[0]["code"].upper():
                guild = self.bot.get_guild(rows[0]["guild_id"])
                with db._conn() as conn:
                    conn.execute("DELETE FROM image_captchas WHERE user_id=?", (message.author.id,))
                    conn.execute("DELETE FROM captcha_join_attempts WHERE user_id=?", (message.author.id,))
                if guild is None:
                    await message.channel.send("Server not found. Please try again in the server.")
                    return
                member = guild.get_member(message.author.id)
                if member is None:
                    await message.channel.send("You are not in the server anymore.")
                    return
                ok = await _verify_member(guild, member, "image captcha")
                await message.channel.send("✅ Correct! You are verified!" if ok else "No verified role found on this server.")
            else:
                # Koolwiza-style attempt limit: 3 wrong tries per
                # 10-minute window, then the code is invalidated and
                # the user must request a new one (button / rejoin
                # flow). No kick: failing a captcha 3 times is not
                # proof of being a bot, and kicking is destructive.
                guild_id = rows[0]["guild_id"]
                now_iso = db.now()
                with db._conn() as conn:
                    attempt = conn.execute(
                        "SELECT attempts, window_start FROM captcha_join_attempts WHERE user_id=? AND guild_id=?",
                        (message.author.id, guild_id)).fetchone()
                    if attempt is None:
                        conn.execute("INSERT INTO captcha_join_attempts VALUES (?, ?, 1, ?)",
                                     (message.author.id, guild_id, now_iso))
                        attempts = 1
                    else:
                        try:
                            start = datetime.fromisoformat(attempt["window_start"])
                            if start.tzinfo is None:
                                start = start.replace(tzinfo=timezone.utc)
                            fresh = (datetime.now(timezone.utc) - start) <= timedelta(minutes=10)
                        except Exception:
                            fresh = False
                        if fresh:
                            attempts = attempt["attempts"] + 1
                            conn.execute("UPDATE captcha_join_attempts SET attempts=? WHERE user_id=? AND guild_id=?",
                                         (attempts, message.author.id, guild_id))
                        else:
                            attempts = 1
                            conn.execute("UPDATE captcha_join_attempts SET attempts=1, window_start=? WHERE user_id=? AND guild_id=?",
                                         (now_iso, message.author.id, guild_id))
                if attempts >= 3:
                    with db._conn() as conn:
                        conn.execute("DELETE FROM image_captchas WHERE user_id=?", (message.author.id,))
                        conn.execute("DELETE FROM captcha_join_attempts WHERE user_id=?", (message.author.id,))
                    await message.channel.send(
                        "❌ Wrong code 3 times. This captcha is now invalid. "
                        "Please click Verify in #verification to get a new one.")
                else:
                    await message.channel.send(f"❌ Wrong code. Try again ({3 - attempts} tries left).")
            return
        guild, author = message.guild, message.author
        if is_staff(author):
            return
        # Anti-link / anti-invite / banned words
        content = message.content
        try:
            if db.get_setting(guild.id, "anti_link") == "on" and re.search(r"https?://", content):
                await message.delete(); await message.channel.send(f"{author.mention} links are not allowed here.", delete_after=10)
                await self._record_violation(guild, author, "link"); return
            if db.get_setting(guild.id, "anti_invite") == "on" and "discord.gg/" in content:
                await message.delete()
                await self._record_violation(guild, author, "invite"); return
            with db._conn() as conn:
                words = [r["word"] for r in conn.execute("SELECT word FROM banned_words WHERE guild_id=?", (guild.id,)) if r["word"].strip()]
            # Word-boundary matching: a banned substring inside an innocent
            # word must not trigger deletion.
            if any(re.search(rf"\b{re.escape(w.lower())}\b", content.lower()) for w in words):
                await message.delete()
                await self._record_violation(guild, author, "banned_word"); return
        except discord.HTTPException:
            return
        # Anti-spam: >5 messages in 10s
        if db.get_setting(guild.id, "anti_spam") == "on":
            now = time.time()
            times = [t for t in self._msg_times[author.id] if now - t < 10]
            times.append(now); self._msg_times[author.id] = times
            if len(times) > 5:
                try:
                    await message.delete()
                    await message.channel.send(f"{author.mention} slow down, you are sending messages too fast.", delete_after=10)
                    await self._record_violation(guild, author, "spam")
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        age_days = (datetime.now(timezone.utc) - member.created_at).days
        min_age = int(db.get_setting(member.guild.id, "min_account_age_days", "0"))
        from cogs.modlog import log_action
        await log_action(member.guild, "Joined", member, None, "New member joined",
                         extra=f"Account age: {age_days} days")
        if db.get_setting(member.guild.id, "anti_raid") == "on" and min_age and age_days < min_age:
            muted = [r for r in member.guild.roles if categorize_role(r, member.guild) == "muted"]
            if muted:
                await member.add_roles(*muted, reason="Anti-raid: new account")
        # Verification gate (Appy-style): a new human member gets the
        # Unverified role on join and therefore cannot see/access
        # anything except #rules / #verification, because almost every
        # category/channel denies View to the Unverified role. They
        # gain access only by clicking Verify Me (which adds Verified
        # and removes Unverified). Bots are skipped: bot accounts join
        # with their own bot roles, not the human gate.
        if not member.bot:
            try:
                verified = [r for r in member.guild.roles if categorize_role(r, member.guild) == "verified"]
                unverified = [r for r in member.guild.roles if categorize_role(r, member.guild) == "unverified"]
                has_verified = any(r in member.roles for r in verified)
                has_unverified = any(r in member.roles for r in unverified)
                if unverified and not has_verified and not has_unverified:
                    await member.add_roles(*unverified, reason="Verification gate: new member")
            except discord.HTTPException:
                pass
            # Auto-DM on join (user request 2026-10-31): every new
            # human member is DM'd and told to verify in
            # #verification to access NEWR LABS. This runs even
            # when captcha-on-join is off, and never breaks the
            # join flow: if DMs are closed, the member can still
            # verify via the #verification panel in-server.
            try:
                from cogs.ui import panel as _panel
                verify_ch = None
                for ch in member.guild.text_channels:
                    if "verif" in ch.name.lower():
                        verify_ch = ch
                        break
                if verify_ch is None:
                    verify_ch = member.guild.get_channel(1471125629259878543)
                verify_mention = verify_ch.mention if verify_ch is not None else "#✔️-verification"
                await member.send(embed=_panel(
                    "Welcome to NEWR LABS!",
                    f"Hi {member.mention}, welcome! You currently have the "
                    f"Unverified role, so you cannot access the server yet.\n\n"
                    f"To get access, go to {verify_mention} in NEWR LABS "
                    f"and click **Verify Me**, then solve the captcha. "
                    f"Once you verify, you will get the Verified role and "
                    f"can see the whole server.",
                    0x5865F2))
            except Exception:
                pass
            # Koolwiza / Sapph captcha-on-join: if enabled, DM the
            # new member an image captcha immediately. Solving it
            # verifies them (same DM handler as the image captcha on join).
            # If DMs are closed, nothing breaks: the member can
            # still verify via the #verification panel.
            if db.get_setting(member.guild.id, "captcha_on_join") == "on":
                import io as _io
                import random as _random
                import string as _string
                alphabet = "".join(c for c in _string.ascii_uppercase + _string.digits if c not in "01IO")
                code = "".join(_random.choice(alphabet) for _ in range(5))
                with db._conn() as conn:
                    conn.execute(
                        "INSERT INTO image_captchas VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(user_id, guild_id) DO UPDATE SET code=excluded.code, created_at=excluded.created_at",
                        (member.id, member.guild.id, code, db.now()))
                try:
                    await member.send(
                        f"🔒 Welcome to {member.guild.name}! Prove you are human: type the code shown "
                        f"in the image below as a reply to this DM (10 minutes, 3 tries). "
                        f"Solving it gives you access to the server.",
                        file=discord.File(_io.BytesIO(_make_captcha_image(code)), filename="captcha.png"))
                except discord.HTTPException:
                    pass

    def _toggle(self, interaction: discord.Interaction, key: str, action: str) -> str:
        if action == "status":
            return f"{key} is currently: {db.get_setting(interaction.guild.id, key)}"
        db.set_setting(interaction.guild.id, key, "on" if action == "enable" else "off")
        return f"{key} set to {action}d."

    def _toggle_cmd(self, name: str, desc: str, key: str):
        async def handler(self, interaction: discord.Interaction, action: app_commands.Choice[str]):  # type: ignore
            if not staff_only(interaction):
                await interaction.response.send_message(embed=_denied(), ephemeral=True); return
            await interaction.response.send_message(self._toggle(interaction, key, action.value), ephemeral=True)
        handler.__name__ = name
        return app_commands.command(name=name, description=desc)(
            app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("enable", "disable", "status")])(handler))

    # Verification — ONE unified, captcha-gated panel. /verify and
    # /captcha_verify post the exact same panel, so there is never
    # a separate "verify" panel and a separate "captcha" panel.
    @app_commands.command(name="verify", description="Post the verification panel (captcha-gated)")
    async def verify(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=emb(
            "🔒 Verification",
            "Welcome! To prove you are human and unlock the server:\n"
            "**1.** Click **Verify** below.\n"
            "**2.** Solve the math captcha that pops up.\n"
            "**3.** Get the Verified role automatically — no role is given before a correct answer."),
            view=VerifyView())

    @app_commands.command(name="captcha_verify", description="Post the verification panel (same captcha-gated panel as /verify, staff)")
    async def captcha_verify(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.response.send_message(embed=emb(
            "🔒 Verification",
            "Welcome! To prove you are human and unlock the server:\n"
            "**1.** Click **Verify** below.\n"
            "**2.** Solve the math captcha that pops up.\n"
            "**3.** Get the Verified role automatically — no role is given before a correct answer."),
            view=VerifyView())

    @app_commands.command(name="verify_user", description="Manually verify a member (staff)")
    async def verify_user(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        verified = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "verified"]
        unverified = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "unverified"]
        await member.add_roles(*verified, reason="Manual verification")
        if unverified:
            await member.remove_roles(*unverified, reason="Manual verification")
        await interaction.response.send_message(f"{member.mention} has been verified.")

    # NOTE: /verify_word was retired with the unified verify flow:
    # hidden-word was a separate panel mode, and the user asked
    # for ONE captcha-gated verify flow instead of separate modes.
    # The old hidden_word DB setting is left untouched (harmless).

    @app_commands.command(name="join_check", description="Risk-check a member joining / already in the server")
    async def join_check(self, interaction: discord.Interaction, member: discord.Member):
        age_days = (datetime.now(timezone.utc) - member.created_at).days
        risk = 0
        reasons = []
        if age_days < 7: risk += 40; reasons.append("Account under 7 days old")
        if age_days < 30: risk += 20; reasons.append("Account under 30 days old")
        if member.avatar is None: risk += 20; reasons.append("No avatar")
        if member.bot: risk += 10; reasons.append("Bot account")
        level = "Low" if risk < 30 else "Medium" if risk < 70 else "High"
        await interaction.response.send_message(embed=emb("Join Check", f"{member.mention}\nRisk: {level} ({risk}/100)\n" + "\n".join(reasons) or "No risk flags"), ephemeral=True)

    @app_commands.command(name="suspicious_check", description="List members with accounts under 7 days old (staff)")
    async def suspicious_check(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        now = datetime.now(timezone.utc)
        young = [m for m in interaction.guild.members if (now - m.created_at).days < 7]
        text = "\n".join(f"{m.mention} — {(now - m.created_at).days}d" for m in young[:30]) or "No accounts under 7 days old."
        await interaction.response.send_message(embed=emb("Suspicious Accounts", text), ephemeral=True)

    # Toggles are registered in __init__-style below via explicit commands:
    @app_commands.command(name="anti_spam", description="Enable, disable or check anti-spam (staff)")
    @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("enable", "disable", "status")])
    async def anti_spam(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.response.send_message(self._toggle(interaction, "anti_spam", action.value), ephemeral=True)

    @app_commands.command(name="anti_link", description="Enable, disable or check anti-link (staff)")
    @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("enable", "disable", "status")])
    async def anti_link(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.response.send_message(self._toggle(interaction, "anti_link", action.value), ephemeral=True)

    @app_commands.command(name="anti_invite", description="Enable, disable or check anti-invite (staff)")
    @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("enable", "disable", "status")])
    async def anti_invite(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.response.send_message(self._toggle(interaction, "anti_invite", action.value), ephemeral=True)

    @app_commands.command(name="anti_raid", description="Enable, disable or check anti-raid mode (staff)")
    @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("enable", "disable", "status")])
    async def anti_raid(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.response.send_message(self._toggle(interaction, "anti_raid", action.value), ephemeral=True)

    @app_commands.command(name="captcha_on_join", description="Enable, disable or check captcha-on-join (staff, Koolwiza-style)")
    @app_commands.choices(action=[app_commands.Choice(name=n, value=n) for n in ("enable", "disable", "status")])
    async def captcha_on_join(self, interaction: discord.Interaction, action: app_commands.Choice[str]):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.response.send_message(
            self._toggle(interaction, "captcha_on_join", action.value) +
            (" (new members get an image captcha DM on join; default is off, so enabling this changes the join flow)" if action.value == "enable" else ""),
            ephemeral=True)
    # NOTE: /raid_status was traded for /captcha_on_join (guild cap
    # is 100). /security_status shows the same settings and more.

    @app_commands.command(name="security_status", description="Show all security settings")
    async def security_status(self, interaction: discord.Interaction):
        g = interaction.guild.id
        text = "\n".join(f"{k}: {db.get_setting(g, k)}" for k in ("anti_spam", "anti_link", "anti_invite", "anti_raid", "min_account_age_days", "captcha_on_join"))
        text += "\nverify: unified captcha-gated panel (no direct Verified)"
        await interaction.response.send_message(embed=emb("Security Status", text), ephemeral=True)

    @app_commands.command(name="security_config", description="Set minimum account age in days for new joins (staff)")
    async def security_config(self, interaction: discord.Interaction, min_account_age_days: int):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        db.set_setting(interaction.guild.id, "min_account_age_days", str(max(0, min_account_age_days)))
        await interaction.response.send_message(f"Minimum account age set to {min_account_age_days} days.")

    # Lockdown / slowmode
    @app_commands.command(name="lockdown", description="Lock the current channel (staff)")
    async def lockdown(self, interaction: discord.Interaction):
        if not staff_only(interaction) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
        await interaction.response.send_message("🔒 Channel locked.")

    @app_commands.command(name="unlock", description="Unlock the current channel (staff)")
    async def unlock(self, interaction: discord.Interaction):
        if not staff_only(interaction) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=None)
        await interaction.response.send_message("🔓 Channel unlocked.")

    @app_commands.command(name="lockdown_server", description="Lock all text channels (staff)")
    async def lockdown_server(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        failed = 0
        for ch in interaction.guild.text_channels:
            try:
                await ch.set_permissions(interaction.guild.default_role, send_messages=False)
            except discord.HTTPException:
                failed += 1
        await interaction.followup.send(f"🔒 Server locked." + (f" ({failed} channel(s) failed — check bot permissions.)" if failed else ""), ephemeral=True)

    @app_commands.command(name="unlock_server", description="Unlock all text channels (staff)")
    async def unlock_server(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        await interaction.response.defer(ephemeral=True)
        failed = 0
        for ch in interaction.guild.text_channels:
            try:
                await ch.set_permissions(interaction.guild.default_role, send_messages=None)
            except discord.HTTPException:
                failed += 1
        await interaction.followup.send(f"🔓 Server unlocked." + (f" ({failed} channel(s) failed — check bot permissions.)" if failed else ""), ephemeral=True)

    @app_commands.command(name="slowmode", description="Set slowmode in seconds for the current channel (staff)")
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        if not staff_only(interaction) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        clamped = max(0, min(21600, seconds))
        await interaction.channel.edit(slowmode_delay=clamped)
        await interaction.response.send_message(f"Slowmode set to {clamped} seconds.")

    # Quarantine / trusted / watchlist / banned words
    @app_commands.command(name="quarantine", description="Quarantine a member with the muted role (staff)")
    async def quarantine(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Quarantine"):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        muted = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "muted"]
        if not muted:
            await interaction.response.send_message("No muted role found.", ephemeral=True); return
        await member.add_roles(*muted, reason=reason)
        await interaction.response.send_message(f"{member.mention} quarantined. Reason: {reason}")

    @app_commands.command(name="unquarantine", description="Remove quarantine from a member (staff)")
    async def unquarantine(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        muted = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "muted"]
        await member.remove_roles(*muted, reason="Unquarantine")
        await interaction.response.send_message(f"{member.mention} unquarantined.")

    @app_commands.command(name="trusted_add", description="Give a member a trusted/helper role (staff)")
    async def trusted_add(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        roles = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "trusted"]
        if not roles:
            await interaction.response.send_message("No trusted role found.", ephemeral=True); return
        await member.add_roles(*roles, reason="Trusted")
        await interaction.response.send_message(f"{member.mention} given trusted roles.")

    @app_commands.command(name="trusted_remove", description="Remove trusted roles from a member (staff)")
    async def trusted_remove(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        roles = [r for r in interaction.guild.roles if categorize_role(r, interaction.guild) == "trusted"]
        await member.remove_roles(*roles, reason="Trusted removed")
        await interaction.response.send_message(f"Trusted roles removed from {member.mention}.")

    @app_commands.command(name="watchlist_add", description="Add a member to the security watchlist (staff)")
    async def watchlist_add(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            conn.execute("INSERT INTO watchlist VALUES (?, ?, ?) ON CONFLICT(guild_id, user_id) DO UPDATE SET reason=excluded.reason",
                         (interaction.guild.id, member.id, reason))
        await interaction.response.send_message(f"{member.mention} added to the watchlist.")

    @app_commands.command(name="watchlist_list", description="List the security watchlist (staff)")
    async def watchlist_list(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        rows = db.list_rows("watchlist", interaction.guild.id, 50)
        text = "\n".join(f"<@{r['user_id']}>: {r['reason']}" for r in rows) or "Watchlist empty."
        await interaction.response.send_message(embed=emb("Watchlist", text), ephemeral=True)

    @app_commands.command(name="watchlist_remove", description="Remove a member from the watchlist (staff)")
    async def watchlist_remove(self, interaction: discord.Interaction, member: discord.Member):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            conn.execute("DELETE FROM watchlist WHERE guild_id=? AND user_id=?", (interaction.guild.id, member.id))
        await interaction.response.send_message(f"{member.mention} removed from the watchlist.")

    @app_commands.command(name="ban_word_add", description="Add a banned word (staff)")
    async def ban_word_add(self, interaction: discord.Interaction, word: str):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        if not word.strip():
            await interaction.response.send_message("Banned word cannot be empty (an empty word would match everything).", ephemeral=True); return
        with db._conn() as conn:
            conn.execute("INSERT OR IGNORE INTO banned_words VALUES (?, ?)", (interaction.guild.id, word.lower()))
        await interaction.response.send_message(f"Banned word added: {word}")

    @app_commands.command(name="ban_word_list", description="List banned words (staff)")
    async def ban_word_list(self, interaction: discord.Interaction):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            rows = conn.execute("SELECT word FROM banned_words WHERE guild_id=?", (interaction.guild.id,)).fetchall()
        text = ", ".join(r["word"] for r in rows) or "No banned words."
        await interaction.response.send_message(embed=emb("Banned Words", text), ephemeral=True)

    @app_commands.command(name="ban_word_remove", description="Remove a banned word (staff)")
    async def ban_word_remove(self, interaction: discord.Interaction, word: str):
        if not staff_only(interaction):
            await interaction.response.send_message(embed=_denied(), ephemeral=True); return
        with db._conn() as conn:
            conn.execute("DELETE FROM banned_words WHERE guild_id=? AND word=?", (interaction.guild.id, word.lower()))
        await interaction.response.send_message(f"Banned word removed: {word}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Security(bot))
