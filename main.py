# ============================================
# main.py - JARVIS Voice Mode
#   Sleep mode : "Hey Jarvis" / "Jarvis wake up" ka intezaar (offline)
#   Active mode: command suno -> Gemini se poocho (wo zarurat ho to tools
#                chalata hai) -> jawab bolo
#   "Jarvis sleep"    -> wapas sleep mode
#   "Jarvis shutdown" -> "Sir, main band ho jaun?" -> haan -> JARVIS band
#   "PC shutdown karo" -> shutdown_pc tool (apna confirmation) - JARVIS nahi
# ============================================

import json     # UI ke confirm() ko sawaal bhejne ke liye
import os       # Window band hone pe poora program band karne ke liye
import re       # Lamba jawab sentences mein todne ke liye
import sys
import threading  # Voice loop aur stats alag thread mein (UI hang na ho)
import time     # Latency (jawab aane mein kitna time laga) naapne ke liye

# pythonw (Windows startup, koi terminal nahi) mein stdout/stderr None hote hain - print crash na kare
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

# Terminal mein Hindi/emoji jaise characters print karte waqt crash na ho
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import brain    # Gemini (dimaag)
import scheduler      # Reminders / tasks (tasks.json + background thread)
import notifications  # WhatsApp ke aaye messages (Windows notifications, sirf RAM mein)
import tools    # Tools (confirm function yahan set karte hain)
import ui       # Screen pe status
import voice    # Sunna aur bolna

# Jaagne pe JARVIS ki pehli line (UI ki wake animation bhi yahi dikhati hai)
WAKE_LINE = "Yes sir, main sun raha hoon"

# Brain ek waqt pe ek hi sawaal sambhale - bol ke poocha (voice thread) aur type
# karke poocha (UI chat box) ek saath aaye to history/tools gadbad na ho
brain_lock = threading.Lock()


# "Haan" maanne wale words (confirmation ke liye)
YES_WORDS = {"yes", "yeah", "yep", "haan", "han", "ha", "haa", "pakka", "sure",
             "ok", "okay", "confirm", "kar", "karo", "do", "हां", "हाँ", "पक्का"}

# "Jarvis" aur uske roop jo Google kabhi-kabhi galat sun leta hai
JARVIS_NAMES = {"jarvis", "jervis", "jarvi", "jarvish", "javis", "jarwis", "jarves",
                "jarvees", "travis", "service", "जार्विस", "जारविस"}

# In words ke saath "shutdown/band" bola to matlab PC band karna hai, JARVIS nahi
PC_WORDS = {"pc", "computer", "laptop", "system", "कंप्यूटर", "पीसी"}

# JARVIS ko band karne / sulane wale phrases
EXIT_PHRASES = ("shutdown", "shut down", "band ho jao", "band ho ja", "band ho jaao",
                "exit", "quit", "बंद हो जाओ")
SLEEP_PHRASES = ("sleep", "so jao", "so ja", "so jaao", "chup raho", "chup ho jao",
                 "सो जाओ", "चुप रहो", "चुप हो जाओ")
# Bina "jarvis" ke bhi ye poora command bola to JARVIS sleep (PC sleep nahi)
NAMELESS_SLEEP = re.compile(
    r"(sleep mode( on| chalu| karo| kar do)?|go to sleep|sleep ho jao|sleep ho ja|"
    r"so jao|so jaao|so ja|chup ho jao|chup raho|bilkul chup raho|ab chup raho|"
    r"सो जाओ|चुप हो जाओ|चुप रहो)")


def control_command(text):
    """"Jarvis shutdown" -> "shutdown", "Jarvis sleep" -> "sleep", warna None.
    Sirf tab jab command mein "jarvis" (ya galat suna roop) ho, command chhota
    ho (6 words tak), aur PC/computer ka zikr NA ho. Isliye:
      "ka shutdown"        -> None (jarvis nahi bola)  -> AI/shortcut
      "PC shutdown kar do" -> None (PC ka zikr hai)    -> shutdown_pc tool (confirm ke saath)
      "mujhe sleep ke tips do" -> None                 -> AI"""
    lower = text.lower()
    words = set(re.findall(r"[^\s.,!?।]+", lower))

    # Bina naam ke bhi: "sleep mode on", "go to sleep", "so jao", "chup ho jao".
    # PC ko sulane ka koi tool nahi hai, isliye iska matlab JARVIS ka sleep hi hai.
    # (Sleep safe hai - "Hey Jarvis" bolke wapas jaga sakte ho)
    if not (words & PC_WORDS) and NAMELESS_SLEEP.fullmatch(" ".join(re.findall(r"[^\s.,!?।]+", lower))):
        return "sleep"

    if not (words & JARVIS_NAMES) or (words & PC_WORDS) or len(lower.split()) > 6:
        return None
    if any(p in lower for p in EXIT_PHRASES):
        return "shutdown"
    if any(p in lower for p in SLEEP_PHRASES):
        return "sleep"
    return None


# Jaagte hue sirf JARVIS ko pukaara ("hey jarvis", "jarvis wake up") - ye AI ko nahi jaata
CALL_WORDS = JARVIS_NAMES | {"hey", "hi", "hello", "ok", "okay", "wake", "up", "utho", "suno",
                             "are", "arey", "haan"}

# Itne second tak kuch samajh na aaye to apne aap sleep mode
IDLE_SLEEP_SECONDS = 20


def is_just_calling(text):
    """True agar command sirf JARVIS ko bulana hai, jaise "hey jarvis" / "jarvis wake up"."""
    words = set(re.findall(r"[^\s.,!?।]+", text.lower()))
    return bool(words & JARVIS_NAMES) and words <= CALL_WORDS


def confirm_exit():
    """JARVIS band hone se pehle ek baar poochho. True = haan, band ho jao."""
    if voice_confirm("Sir, main band ho jaun?"):
        return True
    ui.set_state("speaking")
    voice.speak("Theek hai sir, main yahin hoon.", cache=True)
    return False


# Confirmation ("Sir, pakka?") ka sawaal + jawab ka intezaar kitna chala (latency se alag)
confirm_wait_seconds = 0.0

# "Sir, pakka?" ke baad itne second tak jawab ka intezaar, phir cancel
CONFIRM_WAIT_SECONDS = 5


def voice_ask(question):
    """Sawaal bolo aur POORA jawab (text) lo - jaise "haan" / "thoda polite bana do".
    (WhatsApp message confirm ke liye; jawab na mile to None = cancel)"""
    global confirm_wait_seconds
    started = time.time()
    ui.set_state("speaking")
    voice.speak(question, private=True)     # Sawaal mein message ka text hai - terminal mein nahi
    ui.set_state("listening")
    answer = voice.listen_command(wait_seconds=CONFIRM_WAIT_SECONDS + 2)
    confirm_wait_seconds += time.time() - started
    if not answer:
        ui.log("Jawab nahi mila -> cancel")
        return None
    print(f"Krish: {answer}")
    ui.add_message("user", answer)
    return answer


def announce_messages(on_wake=False):
    """Naye WhatsApp messages batao. Sirf BATATE hain - reply kabhi apne aap nahi.
    on_wake=True: sleep mein aaye messages ki sirf ginti ("Sir, 3 naye messages hain")."""
    new = notifications.take_new()
    if not new:
        return
    ui.set_state("speaking")
    if on_wake or len(new) > 1:
        voice.speak(f"Sir, {len(new)} naye WhatsApp messages hain. 'Messages padho' boliye." if len(new) > 1
                    else f"Sir, {new[0]['sender']} ka ek naya message hai. 'Messages padho' boliye.")
        # Ye abhi padhe nahi gaye - 'messages padho' pe milenge
        return
    m = new[0]
    notifications.mark_read(m["sender"])
    notifications.awaiting_reply = True          # Agla "haan, bol do ki..." isi ka reply
    voice.speak(f"Sir, {m['sender']} ka message aaya: '{m['text']}'. Reply karun?", private=True)


def announce_missed():
    """Jagne pe: band/sleep-PC ke dauran chhoote reminders ("Sir, 2 reminders miss ho gaye the")."""
    items = scheduler.pop_missed()
    if not items:
        return
    ui.set_state("speaking")
    texts = "; ".join(t["what"] for t in items[:3])
    voice.speak(f"Sir, {len(items)} reminder{'s' if len(items) > 1 else ''} miss ho gaye the: {texts}.",
                private=True)        # Reminder ka text terminal mein nahi


_RISKY_REMINDER = re.compile(r"whatsapp|message|msg|call|bhej|send|shutdown|restart|lock|band|close|delete|hata",
                             re.IGNORECASE)


def announce_reminders():
    """Jaagte hue jo reminder ka time aa gaya use seedha bolo. Kaam wala reminder ("weather batana")
    ho to chalao - par WhatsApp/call/shutdown jaisa kaam ho to pehle Krish se poochke (khud kabhi nahi)."""
    for t in scheduler.pop_due():
        ui.set_state("speaking")
        voice.speak(f"Sir, reminder: {t['what']}.", private=True)     # Text terminal mein nahi
        if t.get("kind") != "act":
            continue
        if _RISKY_REMINDER.search(t["what"]):
            answer = voice_ask(f"Sir, reminder ke hisaab se: {t['what']}. Chalaun?")
            if not (answer and set(re.findall(r"[^\s.,!?।]+", answer.lower())) & YES_WORDS):
                voice.speak("Theek hai sir, nahi chalaya.", cache=True)
                continue
        try:
            reply = brain.ask(t["what"])
        except Exception as e:
            reply = None
            ui.log(f"Reminder ka kaam nahi chala: {e}")
        if reply:
            private, tools.private_reply = tools.private_reply, False
            voice.speak(short_for_speech(reply), private=private)


def notify_sleeping(task):
    """Sleep mein reminder: halka chime + chhota notification (HUD toast + tray). JARVIS jagta nahi,
    window fullscreen nahi hoti."""
    voice.chime()
    ui.notify("Reminder: " + task["what"])


def voice_confirm(question):
    """Khatarnak kaam se pehle bol ke poochho, jawab suno. True = haan."""
    global confirm_wait_seconds
    started = time.time()
    ui.set_state("speaking")
    voice.speak(question, cache=True)     # Sawaal hamesha same hote hain -> save karke dobara use
    ui.set_state("listening")
    answer = voice.listen_command(wait_seconds=CONFIRM_WAIT_SECONDS)
    # Latency mein ye time alag dikhana hai (ye aapke jawab ka intezaar hai, brain ka time nahi)
    confirm_wait_seconds += time.time() - started
    if not answer:
        ui.log("Confirmation ka jawab nahi mila -> cancel")
        return False
    print(f"Krish: {answer}")
    ui.add_message("user", answer)
    # Space/punctuation pe todo (\w Hindi matra ko nahi pakadta, isliye ye tareeka)
    words = set(re.findall(r"[^\s.,!?।]+", answer.lower()))
    # "nahi"/"no"/"mat" bola to pakka nahi
    if words & {"no", "nahi", "nahin", "mat", "cancel", "नहीं"}:
        return False
    return bool(words & YES_WORDS)


def short_for_speech(text, max_chars=350):
    """Jawab bahut lamba ho to sirf pehle kuch sentences bolo.
    (Poora jawab terminal mein print ho jaata hai.)"""
    if len(text) <= max_chars:
        return text
    sentences = re.split(r"(?<=[.!?।])\s+", text)
    short = ""
    for s in sentences:
        if short and len(short) + len(s) > max_chars:
            break
        short += s + " "
    return short.strip()


def active_mode():
    """Jaagne ke baad commands sunta hai.
    Return: "sleep" (wapas sone jao) ya "shutdown" (band karo)."""
    global confirm_wait_seconds

    ui.set_state("speaking")
    voice.speak(WAKE_LINE, cache=True)
    announce_messages(on_wake=True)   # Sleep mein aaye messages: "Sir, 3 naye messages hain"
    announce_missed()                 # Chhoote reminders: "Sir, 2 reminders miss ho gaye the"

    last_heard = time.time()     # Aakhri baar kab kuch samajh aaya (auto-sleep ke liye)
    pending = None               # Spelling sunte waqt aaya alag command (agli baar chalega)

    while True:
        announce_messages()      # Jaagte hue naya message aaya ho to batao (reply nahi)
        announce_reminders()     # Reminder ka time aaya ho to bolo
        ui.set_state("listening")
        # Utna hi intezaar karo jitna auto-sleep tak bacha hai (max 8s ek baar mein)
        remaining = IDLE_SLEEP_SECONDS - (time.time() - last_heard)
        if pending:                   # Spelling ke beech suna gaya alag command pehle
            command, pending = pending, None
        else:
            command = voice.listen_command(wait_seconds=max(1.0, min(8.0, remaining)))

        # Koi kuch nahi bola ya samajh nahi aaya - AI ko kuch mat bhejo
        if not command or not command.strip():
            if time.time() - last_heard >= IDLE_SLEEP_SECONDS:
                ui.log(f"{IDLE_SLEEP_SECONDS}s tak kuch nahi suna -> sleep mode")
                ui.set_state("speaking")
                voice.speak("Main so raha hoon sir, zarurat ho to bula lena.", cache=True)
                return "sleep"
            continue

        # --- Spelling beech mein kat gayi? ("...username hai Ke r r i") ---
        # Dheere-dheere akshar bolte waqt pause pe recording ruk jaati hai - to aage
        # sunte raho aur jodte raho (max 3 baar, bina beep ke)
        for _ in range(3):
            if not brain.ends_mid_spelling(command):
                break
            ui.log("Spelling chal rahi hai - aage sun raha hoon...")
            more = voice.listen_command(wait_seconds=4)
            if not more:
                break
            if not brain.continues_spelling(more):
                pending = more        # Ye spelling nahi, naya command hai - agli baar chalao
                break
            command = f"{command} {more}"

        last_heard = time.time()
        print(f"Krish: {tools.mask_private(command)}")
        ui.add_message("user", command)
        heard_at = time.time()        # Latency yahan se ginna shuru (command sun liya)
        command_stt = voice.last_stt_seconds   # (confirm wala sunna baad mein isse overwrite kar deta)
        confirm_wait_seconds = 0.0

        # --- Sirf "hey jarvis" bola (JARVIS pehle se jaag raha hai) -> bina AI ke ---
        if is_just_calling(command):
            ui.log("Just calling JARVIS (no AI)")
            ui.set_state("speaking")
            voice.speak("Haan sir?", cache=True)
            continue

        # --- Control commands ("Jarvis shutdown" / "Jarvis sleep") ---
        control = control_command(command)
        if control == "shutdown":
            if confirm_exit():
                return "shutdown"
            continue
        if control == "sleep":
            ui.set_state("speaking")
            voice.speak("Theek hai sir, zarurat ho to bula lena.", cache=True)
            return "sleep"

        # --- Baaki sab brain ko (shortcut -> Gemini -> Groq) ---
        ui.set_state("thinking")
        try:
            with brain_lock:
                reply = brain.ask(command)
        except Exception as e:
            print(f"(Brain error: {e})")
            ui.set_state("speaking")
            voice.speak("Sorry sir, abhi kuch gadbad ho gayi. Phir se boliye.", cache=True)
            continue
        if not reply:
            continue
        # Brain ka asli time = kul time - confirmation ka intezaar
        brain_seconds = time.time() - heard_at - confirm_wait_seconds

        # Poora jawab print karo, bolo sirf chhota version
        if len(reply) > 350:
            print(f"(Poora jawab: {reply})")
        ui.set_state("speaking")
        # WhatsApp message padh ke sunaya ho to terminal mein text mat chhapo
        private, tools.private_reply = tools.private_reply, False
        # Barge-in / Esc se beech mein rok diya gaya to baki latency ka hisaab
        # bekaar hai - seedha wapas sunne (listening) par chale jao
        if not voice.speak(short_for_speech(reply) if not private else reply, private=private):
            ui.log("Jawab beech me ruk diya gaya - wapas sun raha hoon")
            continue

        # --- Latency: sunne ke baad awaaz shuru hone tak kitna time laga ---
        total = command_stt + brain_seconds + voice.last_tts_seconds
        extra = (f"  (+ confirmation ka intezaar {confirm_wait_seconds:.1f}s alag)"
                 if confirm_wait_seconds else "")
        print(f"  [Latency] Google sunna {command_stt:.1f}s + "
              f"brain ({brain.last_brain}) {brain_seconds:.1f}s + "
              f"awaaz banana {voice.last_tts_seconds:.1f}s = {total:.1f}s{extra}")


def voice_loop():
    """Awaaz wala loop: sleep mode <-> active mode. (UI ke saath alag thread mein chalta hai)"""
    # Tools ko batao ki confirmation / sawaal bol ke poochne hain
    tools.confirm = voice_confirm
    tools.ask_user = voice_ask
    scheduler.hooks["sleep"] = notify_sleeping
    scheduler.start()             # Ek background thread, har 20s mein tasks.json dekhta hai
    if notifications.status() == "not started":
        notifications.start()     # WhatsApp notifications padhna (sirf RAM mein)

    while True:
        # --- Sleep mode: chupchap wake word suno ---
        ui.set_state("sleeping")
        ui.hide_window()  # Sleep mein window chhupi rahe (JARVIS tray mein chalta hai)
        print("\n[Sleep mode] 'Hey Jarvis' ya 'Jarvis wake up' bolo "
              "('Jarvis shutdown' = band)")
        if voice.wait_for_wake_word() == "shutdown":
            if confirm_exit():
                break
            continue      # "Nahi" bola -> wapas sleep mode

        ui.wake()         # Window saamne + flash + panels slide-in

        # --- Active mode ---
        scheduler.awake = True        # Reminder ab seedha bola jaayega
        try:
            result = active_mode()
        finally:
            scheduler.awake = False   # Sleep mein reminder = chime + notification
        if result == "shutdown":
            break

    ui.set_state("speaking")
    voice.speak("Shutting down. Goodbye sir.", cache=True)


# ============================================
# 3D UI (pywebview) - ui/index.html
# ============================================
UI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")


class Api:
    """HTML ka JavaScript isko bulata hai: window.pywebview.api.ask(text)
    (UI chat box mein type karke poocha sawaal)."""

    def ask(self, text):
        text = (text or "").strip()
        if not text:
            return ""
        print(f"Krish (typed): {tools.mask_private(text)}")
        with brain_lock:
            # Type karke poocha hai to "Sir, pakka?" bhi screen pe poocho, bol ke nahi
            old_confirm, tools.confirm = tools.confirm, ui_confirm
            old_ask, tools.ask_user = tools.ask_user, ui_prompt
            try:
                reply = brain.ask(text) or ""
            except Exception as e:
                print(f"(Brain error: {e})")
                reply = "Sorry sir, abhi kuch gadbad ho gayi."
            finally:
                tools.confirm, tools.ask_user = old_confirm, old_ask
        private, tools.private_reply = tools.private_reply, False
        print("JARVIS (typed reply): [private]" if private else f"JARVIS (typed reply): {reply}")
        ui.log(f"Brain: {brain.last_brain}")
        return reply

    def hide(self):
        """Esc dabane pe bolna rok do aur window chhupao (background mein chalta rahe)."""
        voice.stop_speaking()
        ui.hide_window()

    def stop(self):
        """HUD ke STOP button / Esc: sirf bolna rok do (window khuli rahe)."""
        voice.stop_speaking()


def ui_prompt(question):
    """UI mein prompt() box - jawab type karo (jaise "haan" ya "polite bana do"). Cancel = None."""
    try:
        return ui.window.evaluate_js(f"prompt({json.dumps(question, ensure_ascii=False)}, 'haan')")
    except Exception:
        return None


def ui_confirm(question):
    """UI mein browser wala confirm() dialog (OK = haan, Cancel = nahi)."""
    try:
        return bool(ui.window.evaluate_js(f"confirm({json.dumps(question, ensure_ascii=False)})"))
    except Exception:
        return False


def stats_loop():
    """Har 2 second CPU, RAM, battery, disk, network UI ko bhejo."""
    import psutil
    psutil.cpu_percent(interval=None)          # Pehli reading hamesha 0 aati hai - chhod do
    drive = os.path.splitdrive(os.path.abspath(__file__))[0] + os.sep   # Jis drive pe JARVIS hai
    last, last_t = psutil.net_io_counters(), time.time()
    while True:
        time.sleep(2)
        if not ui.is_visible():
            last, last_t = psutil.net_io_counters(), time.time()   # Chhupi window: naapna bhi band (CPU bachao)
            continue
        battery = psutil.sensors_battery()
        # Network: pichle 2 second mein kitne bytes aaye+gaye -> MB/s
        now, now_t = psutil.net_io_counters(), time.time()
        moved = (now.bytes_recv - last.bytes_recv) + (now.bytes_sent - last.bytes_sent)
        net_mbps = round(moved / max(now_t - last_t, 0.1) / 1e6, 2)
        last, last_t = now, now_t
        try:
            disk = round(psutil.disk_usage(drive).percent)
        except Exception:
            disk = None
        ui.set_stats(round(psutil.cpu_percent(interval=None)),
                     round(psutil.virtual_memory().percent),
                     round(battery.percent) if battery else None,
                     disk, net_mbps)


# ============================================
# System tray icon (pystray): Show Jarvis / Quit
# ============================================
def _tray_image():
    """Tray ke liye chhota gol neela icon (koi file nahi - yahin banta hai)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, 60, 60), outline=(31, 169, 255, 255), width=5)
    d.ellipse((20, 20, 44, 44), fill=(143, 227, 255, 255))
    return img


def start_tray():
    """Tray icon alag thread mein. 'Show Jarvis' = window dikhao, 'Quit' = sab band."""
    import pystray
    icon = pystray.Icon(
        "jarvis", _tray_image(), "J.A.R.V.I.S",
        menu=pystray.Menu(
            pystray.MenuItem("Show Jarvis", lambda: ui.show_window(), default=True),
            pystray.MenuItem("Quit", lambda: exit_now()),
        ),
    )
    threading.Thread(target=icon.run, daemon=True, name="tray").start()
    return icon


def exit_now():
    """Poora JARVIS band (mic/threads ka intezaar kiye bina)."""
    print("\nJARVIS band.")
    sys.stdout.flush()
    os._exit(0)


def start_with_ui():
    """Window kholo; voice loop + stats alag threads mein chalao."""
    import webview

    # Frameless + fullscreen + shuru mein chhupi. "Jarvis wake up" pe saamne aati hai.
    ui.window = webview.create_window("J.A.R.V.I.S", UI_FILE, js_api=Api(),
                                      fullscreen=True, frameless=True, hidden=True,
                                      background_color="#020a14")
    ui.window.events.closed += exit_now        # Window sach mein band (Alt+F4) -> JARVIS band
    icon = start_tray()
    ui.tray_notify = lambda title, msg: icon.notify(msg, title)     # Sleep mein chhota notification
    print("JARVIS background mein chal raha hai (tray icon: Show Jarvis / Quit)")

    def background():
        ui.window.events.loaded.wait(20)        # HTML load hone tak ruko
        ui.current_state = None                 # Taaki pehla "sleeping" bhi UI tak jaaye (jarvis.sleep())
        if tools.DRY_RUN:
            ui.log("[DRY RUN] shutdown/restart/lock/close_app sirf print honge")
        threading.Thread(target=stats_loop, daemon=True).start()
        try:
            voice_loop()
        except Exception as e:
            print(f"(Voice loop error: {e})")
        # "Jarvis shutdown" -> window bhi band (closed event exit_now chalayega)
        try:
            ui.window.destroy()
        except Exception:
            exit_now()

    webview.start(background)                   # Ye window band hone tak yahin rukta hai
    exit_now()


# Program yahan se shuru hota hai
if __name__ == "__main__":
    try:
        if os.path.exists(UI_FILE):
            start_with_ui()
        else:
            print(f"(UI file nahi mili: {UI_FILE} - sirf terminal mode)")
            voice_loop()
    except KeyboardInterrupt:
        # Ctrl+C dabane pe bina error ke band ho
        exit_now()
