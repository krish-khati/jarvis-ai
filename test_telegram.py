# Telegram bot test: DRY_RUN=1, nakli updates/bot (internet/token nahi chahiye)
import asyncio, os, sys
from types import SimpleNamespace as NS
os.environ["DRY_RUN"] = "1"
os.environ["TELEGRAM_ALLOWED_USER_IDS"] = "111"
import tools, telegram_bot as tb
import brain
assert tools.DRY_RUN

sent = []          # (kind, text)
class FakeMsg:
    async def edit_reply_markup(self, m): pass
class FakeBot:
    async def send_message(self, chat, text, reply_markup=None):
        sent.append(("msg", text, reply_markup is not None)); return FakeMsg()
def upd(uid, text):
    async def reply_text(t): sent.append(("reply", t))
    async def reply_photo(p): sent.append(("photo", len(p.getvalue())))
    return NS(effective_user=NS(id=uid), effective_chat=NS(id=uid),
              message=NS(text=text, reply_text=reply_text, reply_photo=reply_photo))
ctx = NS(bot=FakeBot())
fails = []
def check(name, cond):
    print(("OK   " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

async def press(bot, choice, delay=0.3):
    for _ in range(100):
        await asyncio.sleep(0.05)
        if bot.pending: break
    key = next(iter(bot.pending))
    async def answer(): pass
    await bot.on_button(NS(effective_user=NS(id=111), callback_query=NS(data=f"{key}:{choice}", answer=answer)), ctx)

async def main():
    # --- nakli brain: CONFIRM flow ---
    calls = []
    def fake_ask(text):
        calls.append(text)
        if text == "confirm test":
            return "Kiya gaya" if tools.confirm("Sir, pakka?") else "Cancel kar diya"
        return "jawab: " + text
    bot = tb.Bot(ask_fn=fake_ask, grab_fn=lambda: b"PNGDATA")
    # 1 allowed user
    sent.clear(); await bot.on_text(upd(111, "namaste"), ctx)
    check("allowed user jawab", ("reply", "jawab: namaste") in sent)
    # 2 unknown user: kuch nahi (reply bhi nahi, brain bhi nahi)
    sent.clear(); n = len(calls); await bot.on_text(upd(999, "namaste"), ctx)
    check("unknown user ignore", sent == [] and len(calls) == n)
    # 3 CONFIRM haan / nahi
    sent.clear(); await asyncio.gather(bot.on_text(upd(111, "confirm test"), ctx), press(bot, "y"))
    check("confirm haan", ("reply", "Kiya gaya") in sent and any(k == "msg" and b for k, _, b in [s for s in sent if s[0]=="msg"]))
    sent.clear(); await asyncio.gather(bot.on_text(upd(111, "confirm test"), ctx), press(bot, "n"))
    check("confirm nahi", ("reply", "Cancel kar diya") in sent)
    # 4 timeout (60 s ko 1 s kiya)
    tb.CONFIRM_TIMEOUT = 1
    sent.clear(); await bot.on_text(upd(111, "confirm test"), ctx)
    check("confirm timeout = cancel", ("reply", "Cancel kar diya") in sent)
    tb.CONFIRM_TIMEOUT = 60
    # 5 unknown user button ignore
    sent.clear(); fut_done = []
    async def cfm():
        bot.loop = asyncio.get_running_loop()
        return await bot._ask_buttons("q")
    t = asyncio.create_task(cfm()); await asyncio.sleep(0.2)
    key = next(iter(bot.pending))
    async def answer(): pass
    await bot.on_button(NS(effective_user=NS(id=999), callback_query=NS(data=f"{key}:y", answer=answer)), ctx)
    check("unknown user button ignore", not bot.pending[key].done())
    await bot.on_button(NS(effective_user=NS(id=111), callback_query=NS(data=f"{key}:n", answer=answer)), ctx)
    check("allowed button", (await t) == "nahi")
    # 6 screenshot: pehle confirm
    sent.clear(); await asyncio.gather(bot.on_text(upd(111, "screenshot bhejo"), ctx), press(bot, "n"))
    check("screenshot nahi = image nahi", not any(s[0] == "photo" for s in sent))
    sent.clear(); await asyncio.gather(bot.on_text(upd(111, "screenshot bhejo"), ctx), press(bot, "y"))
    check("screenshot haan = image", ("photo", 7) in sent)
    # 7 rate limit
    bot2 = tb.Bot(ask_fn=lambda t: "ok"); sent.clear()
    for i in range(31): await bot2.on_text(upd(111, f"m{i}"), ctx)
    check("rate limit 30/ghanta", sum(1 for s in sent if s == ("reply", "ok")) == 30 and "limit" in sent[-1][1])
    # 8 /status
    sent.clear(); await bot.on_status(upd(111, "/status"), ctx)
    check("/status", sent and "PC on hai" in sent[0][1] and "JARVIS" in sent[0][1])
    # 9 NEVER block (asli brain + shortcut, DRY_RUN=1)
    bot3 = tb.Bot(ask_fn=brain.ask)
    for phrase in ("PC shutdown karo", "PC restart karo", "PC lock karo"):
        sent.clear(); await bot3.on_text(upd(111, phrase), ctx)
        r = [s[1] for s in sent if s[0] == "reply"]
        check(f"NEVER block: {phrase}", r and "PC pe hi" in r[0] and not any(s[0]=="msg" for s in sent))
    check("tools.source reset", tools.source == "")
    # 10 voice note (nakli transcribe)
    import numpy as np, soundfile as sf, io
    buf = io.BytesIO(); sf.write(buf, np.zeros(48000, dtype="float32"), 48000, format="OGG", subtype="OPUS")
    async def get_file(fid):
        class F:
            async def download_as_bytearray(self): return bytearray(buf.getvalue())
        return F()
    v = upd(111, None); v.message.voice = NS(file_id="x"); v.message.audio = None
    sent.clear()
    bot4 = tb.Bot(ask_fn=lambda t: "suna: " + t, transcribe_fn=lambda a: "weather batao")
    await bot4.on_voice(v, NS(bot=NS(get_file=get_file, send_message=FakeBot().send_message)))
    check("voice note -> stt -> brain", ("reply", "suna: weather batao") in sent)

asyncio.run(main())
print("\nSAB PASS" if not fails else f"\nFAIL: {fails}")
sys.exit(1 if fails else 0)
