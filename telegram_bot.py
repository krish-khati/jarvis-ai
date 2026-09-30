# telegram_bot.py - Telegram se JARVIS ko command dene ka rasta (Krish ka apna bot, sirf allowed user ID)
#
# Rules (TELEGRAM_TASK.md + CLAUDE.md):
#   - Sirf TELEGRAM_ALLOWED_USER_IDS ke messages; baaki = koi reply nahi, log mein sirf "unknown user"
#   - Text -> brain.ask (shortcut/agent/AI, wahi safety lock + permissions.Guard); voice note -> stt.py
#   - CONFIRM tools: Telegram pe Haan/Nahi buttons, 60 s mein jawab nahi = cancel
#   - NEVER tools (shutdown/restart/lock): Telegram se band ("Ye PC pe hi hoga") - tools.source="telegram"
#   - Screenshot: sirf "Haan" ke baad image bhejta hai
#   - 30 messages/ghanta, /status, alag thread, internet na ho to retry (crash nahi)
#   - Token kabhi print/log nahi; message ka text kabhi log nahi ("telegram command received")
import asyncio
import collections
import io
import itertools
import os
import re
import threading
import time

from dotenv import load_dotenv

import tools
import ui

load_dotenv()

RATE_LIMIT = 30                  # ek ghante mein max messages
RATE_WINDOW = 3600
CONFIRM_TIMEOUT = 60             # Haan/Nahi ka intezaar (second)
RETRY_SECONDS = 30               # internet na ho to dobara koshish
MAX_CHUNK = 3900                 # Telegram ki limit 4096

SCREENSHOT_CMD = re.compile(r"\b(screenshot|screen\s*shot|screen\s+ki\s+(photo|pic|picture))\b", re.I)

started_at = time.time()         # JARVIS kab se chal raha hai (/status)


def enabled():
    return os.getenv("TELEGRAM_ENABLED", "0").strip() == "1"


def token():
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def allowed_ids():
    ids = set()
    for part in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


class RateLimiter:
    """Sliding window: ek ghante mein max `limit` messages."""

    def __init__(self, limit=RATE_LIMIT, window=RATE_WINDOW, clock=time.time):
        self.limit, self.window, self.clock = limit, window, clock
        self.hits = collections.deque()

    def allow(self):
        now = self.clock()
        while self.hits and now - self.hits[0] > self.window:
            self.hits.popleft()
        if len(self.hits) >= self.limit:
            return False
        self.hits.append(now)
        return True


def _fmt_duration(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    return f"{h} ghante {m} minute" if h else f"{m} minute"


def status_text():
    """/status: PC on hai, battery, JARVIS kab se chal raha hai."""
    lines = ["PC on hai."]
    try:
        import psutil
        b = psutil.sensors_battery()
        if b is not None:
            lines.append(f"Battery: {int(b.percent)}%" + (" (charging)" if b.power_plugged else ""))
        else:
            lines.append("Battery: desktop (battery nahi)")
    except Exception:
        lines.append("Battery: pata nahi chala")
    lines.append(f"JARVIS {_fmt_duration(time.time() - started_at)} se chal raha hai.")
    return "\n".join(lines)


def _chunks(text):
    text = text or ""
    return [text[i:i + MAX_CHUNK] for i in range(0, len(text), MAX_CHUNK)] or [""]


def grab_screen_png():
    """Poori screen ki PNG bytes (sirf RAM, disk pe nahi)."""
    from PIL import ImageGrab
    img = ImageGrab.grab(all_screens=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def ogg_to_audio(data):
    """Telegram voice note (ogg/opus bytes) -> sr.AudioData 16 kHz mono (sirf RAM)."""
    import numpy as np
    import soundfile as sf
    import speech_recognition as sr
    pcm, rate = sf.read(io.BytesIO(bytes(data)), dtype="float32", always_2d=True)
    mono = pcm.mean(axis=1)
    if rate != 16000 and len(mono):
        n = int(len(mono) * 16000 / rate)
        mono = np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono)
    raw = (np.clip(mono, -1, 1) * 32767).astype("<i2").tobytes()
    return sr.AudioData(raw, 16000, 2)


class Bot:
    def __init__(self, brain_lock=None, ask_fn=None, transcribe_fn=None, grab_fn=None):
        self.brain_lock = brain_lock or threading.Lock()
        self._ask_fn = ask_fn            # test mein nakli brain.ask
        self._transcribe = transcribe_fn
        self._grab = grab_fn or grab_screen_png
        self.limiter = RateLimiter()
        self.ids = allowed_ids()
        self.loop = None
        self.bot = None                  # telegram.Bot (handlers mein context.bot se set)
        self.chat_id = None
        self.pending = {}                # token -> asyncio.Future (Haan/Nahi ya text jawab)
        self.text_waiting = None         # jis ask_user ko agla text message jawab ke taur pe chahiye
        self._tokens = itertools.count(1)

    # ---------- helpers ----------
    def _ask(self, text):
        if self._ask_fn:
            return self._ask_fn(text)
        import brain
        return brain.ask(text)

    def _note(self):
        print("[Telegram] telegram command received")
        ui.log("Telegram se command aaya")

    async def _reply(self, update, text):
        for part in _chunks(text):
            await update.message.reply_text(part)

    # ---------- Haan / Nahi buttons (brain thread se bulaya jaata hai) ----------
    async def _ask_buttons(self, question, want_text=False):
        """Sawaal + Haan/Nahi buttons. Return "haan" / "nahi" / text jawab / None (60 s mein kuch nahi)."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        key = str(next(self._tokens))
        fut = self.loop.create_future()
        self.pending[key] = fut
        if want_text:
            self.text_waiting = key
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Haan", callback_data=f"{key}:y"),
                                        InlineKeyboardButton("Nahi", callback_data=f"{key}:n")]])
        msg = None
        try:
            msg = await self.bot.send_message(self.chat_id, question, reply_markup=markup)
            return await asyncio.wait_for(fut, CONFIRM_TIMEOUT)
        except asyncio.TimeoutError:
            try:
                await self.bot.send_message(self.chat_id, "60 second mein jawab nahi aaya, cancel kar diya.")
            except Exception:
                pass
            return None
        finally:
            self.pending.pop(key, None)
            if self.text_waiting == key:
                self.text_waiting = None
            if msg is not None:
                try:
                    await msg.edit_reply_markup(None)       # purane buttons hata do
                except Exception:
                    pass

    def _blocking_ask(self, question, want_text=False):
        """Brain thread se bulao: event loop pe sawaal bhejo aur jawab ka intezaar karo."""
        fut = asyncio.run_coroutine_threadsafe(self._ask_buttons(question, want_text), self.loop)
        try:
            return fut.result(CONFIRM_TIMEOUT + 10)
        except Exception:
            return None

    def hook_confirm(self, question):
        return self._blocking_ask(question) == "haan"

    def hook_ask_user(self, question):
        return self._blocking_ask(question, want_text=True)

    # ---------- brain (alag thread, brain_lock ke saath) ----------
    def _run_brain(self, text):
        replies = []
        with self.brain_lock:
            old = (tools.confirm, tools.ask_user, tools.read_out, tools.source)
            tools.confirm = tools.timed_wait(self.hook_confirm)
            tools.ask_user = tools.timed_wait(self.hook_ask_user)
            tools.read_out = lambda t: (replies.append(t) or True)      # "padh ke sunao" = Telegram pe text
            tools.source = "telegram"
            try:
                reply = self._ask(text) or ""
            except Exception as e:
                print(f"[Telegram] brain error: {type(e).__name__}")
                reply = "Sorry sir, abhi kuch gadbad ho gayi."
            finally:
                tools.confirm, tools.ask_user, tools.read_out, tools.source = old
                tools.private_reply = False
        return "\n\n".join(p for p in [*replies, reply] if p)

    async def _process_text(self, update, text):
        self.chat_id = update.effective_chat.id if getattr(update, "effective_chat", None) else self.chat_id
        if SCREENSHOT_CMD.search(text):
            ok = await self._ask_buttons("Sir, screenshot bhejun? (screen pe private cheezein ho sakti hain)")
            if ok != "haan":
                return await self._reply(update, "Theek hai sir, screenshot nahi bheja.")
            try:
                png = await self.loop.run_in_executor(None, self._grab)
                await update.message.reply_photo(io.BytesIO(png))
            except Exception as e:
                print(f"[Telegram] screenshot error: {type(e).__name__}")
                await self._reply(update, "Screenshot nahi ho paya, sir.")
            return
        reply = await self.loop.run_in_executor(None, self._run_brain, text)
        await self._reply(update, reply or "Theek hai sir.")

    # ---------- telegram handlers ----------
    def _authorized(self, update):
        user = getattr(update, "effective_user", None)
        if user is None or user.id not in self.ids:
            print("[Telegram] unknown user (ignored)")
            return False
        return True

    async def on_text(self, update, context):
        if not self._authorized(update):
            return
        self.bot, self.loop = context.bot, asyncio.get_running_loop()
        self.chat_id = update.effective_chat.id
        text = (update.message.text or "").strip()
        if not text:
            return
        if self.text_waiting and self.text_waiting in self.pending:     # chalte ask_user ka jawab
            self.pending[self.text_waiting].set_result(text)
            return
        if not self.limiter.allow():
            return await self._reply(update, "Sir, ek ghante mein 30 messages ki limit poori ho gayi. Thodi der baad bhejna.")
        self._note()
        await self._process_text(update, text)

    async def on_voice(self, update, context):
        if not self._authorized(update):
            return
        self.bot, self.loop = context.bot, asyncio.get_running_loop()
        self.chat_id = update.effective_chat.id
        if not self.limiter.allow():
            return await self._reply(update, "Sir, ek ghante mein 30 messages ki limit poori ho gayi. Thodi der baad bhejna.")
        self._note()
        try:
            media = update.message.voice or update.message.audio
            data = await (await context.bot.get_file(media.file_id)).download_as_bytearray()
            transcribe = self._transcribe
            if transcribe is None:
                import stt
                transcribe = lambda a: stt.transcribe(a)[0]
            audio = await self.loop.run_in_executor(None, ogg_to_audio, data)
            text = await self.loop.run_in_executor(None, transcribe, audio)
        except Exception as e:
            print(f"[Telegram] voice error: {type(e).__name__}")
            return await self._reply(update, "Voice note samajh nahi aaya, sir. Dobara bhejo ya type karo.")
        if not text:
            return await self._reply(update, "Voice note mein kuch suna nahi, sir.")
        if self.text_waiting and self.text_waiting in self.pending:
            self.pending[self.text_waiting].set_result(text)
            return
        await self._process_text(update, text)

    async def on_status(self, update, context):
        if not self._authorized(update):
            return
        if not self.limiter.allow():
            return await self._reply(update, "Sir, ek ghante mein 30 messages ki limit poori ho gayi.")
        await self._reply(update, status_text())

    async def on_button(self, update, context):
        query = update.callback_query
        user = getattr(update, "effective_user", None)
        if user is None or user.id not in self.ids:
            print("[Telegram] unknown user (ignored)")
            return
        key, _, choice = (query.data or "").partition(":")
        fut = self.pending.get(key)
        try:
            await query.answer()
        except Exception:
            pass
        if fut is not None and not fut.done():
            fut.set_result("haan" if choice == "y" else "nahi")

    # ---------- chalana (alag thread) ----------
    def build_app(self):
        from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters)
        app = (Application.builder().token(token()).concurrent_updates(True).build())
        app.add_handler(CommandHandler("status", self.on_status))
        app.add_handler(CallbackQueryHandler(self.on_button))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.on_text))
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.on_voice))
        app.add_error_handler(self.on_error)
        return app

    async def on_error(self, update, context):
        # Sirf error ka type (URL mein token hota hai - message print nahi)
        print(f"[Telegram] error: {type(context.error).__name__}")

    async def _serve(self, stop):
        self.loop = asyncio.get_running_loop()
        while not stop.is_set():
            app = self.build_app()
            try:
                async with app:
                    await app.start()
                    await app.updater.start_polling(drop_pending_updates=True)
                    print("[Telegram] bot chalu")
                    while not stop.is_set():
                        await asyncio.sleep(1)
                    await app.updater.stop()
                    await app.stop()
            except Exception as e:
                print(f"[Telegram] connect nahi hua ({type(e).__name__}), {RETRY_SECONDS}s mein dobara")
                for _ in range(RETRY_SECONDS):
                    if stop.is_set():
                        break
                    await asyncio.sleep(1)

    def run(self, stop):
        asyncio.run(self._serve(stop))


_stop = threading.Event()


def start(brain_lock=None):
    """main.py se: TELEGRAM_ENABLED=1, token aur allowed IDs hon tabhi alag daemon thread mein chalu."""
    if not enabled():
        return None
    if not token() or not allowed_ids():
        print("[Telegram] TELEGRAM_ENABLED=1 hai par token/allowed user ID .env mein nahi - band")
        return None
    import logging
    for name in ("httpx", "httpcore", "telegram", "apscheduler"):
        logging.getLogger(name).setLevel(logging.CRITICAL)      # httpx URL (token ke saath) log karta hai
    bot = Bot(brain_lock)
    t = threading.Thread(target=bot.run, args=(_stop,), daemon=True, name="telegram")
    t.start()
    return bot


def stop():
    _stop.set()
