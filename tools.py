# ============================================
# tools.py - JARVIS ke "haath-pair" (tools)
#
# Gemini khud decide karta hai kaunsa tool kab chalana hai (function calling).
# Gemini har function ka NAAM, uske PARAMETERS aur DOCSTRING (""" ... """)
# padh ke samajhta hai ki tool kya karta hai - isliye docstring English mein
# aur saaf likhe hain. Comments (#) Hinglish mein hain aapke samajhne ke liye.
#
# Har tool ek chhota text (string) return karta hai - Gemini use padh ke
# user ko jawab banata hai.
# ============================================

import datetime            # Time aur date ke liye
import functools           # Decorator banane ke liye (neeche @tool dekho)
import inspect             # Tool ke parameters ke naam padhne ke liye (UI message mein)
import itertools           # Activity panel ke liye kaam ke number (1, 2, 3...)
import json                # Notes ko notes.json mein save karne ke liye
import os                  # Files, folders, apps kholne ke liye
import re                  # Message mein words dhoondhne ke liye (safety lock)
import subprocess          # Windows commands chalane ke liye
import time                # Thoda rukne ke liye (Windows search mein)
import webbrowser          # Browser mein website kholne ke liye
import winreg              # Windows registry se Pictures folder ka rasta nikalne ke liye

import psutil              # Battery, CPU, RAM, aur apps band karne ke liye
from dotenv import load_dotenv   # .env se DRY_RUN setting padhne ke liye

import ui                  # Screen pe status dikhane ke liye


# ============================================
# DRY RUN mode (testing ke liye)
#   .env mein DRY_RUN=1 -> shutdown, restart, lock aur app band karna asli
#   mein NAHI hote, sirf print hota hai ki kya chalta. Normal use: DRY_RUN=0
# ============================================
load_dotenv()
DRY_RUN = os.getenv("DRY_RUN", "0").strip() == "1"

if DRY_RUN:
    print("[DRY RUN] Shutdown/restart/lock/close_app asli mein nahi chalenge, sirf print honge.")


def _dry_run(action):
    """DRY RUN mein asli kaam ki jagah ye message print aur return hota hai."""
    ui.log(f"[DRY RUN] Would run: {action}")
    return (f"DRY RUN (test mode): everything worked and Krish already confirmed, but "
            f"'{action}' was NOT actually run because DRY_RUN=1. Tell Krish in one short "
            f"sentence that it was test mode so nothing really happened. Do not ask to confirm again.")


# ============================================
# Confirmation (khatarnak kaam se pehle "Sir, pakka?")
# ============================================
def confirm(question):
    """Khatarnak kaam se pehle user se poochhta hai. True = haan, False = nahi.
    main.py (voice) aur jarvis.py (text) isko apne tareeke se badal dete hain.
    Default: hamesha "nahi" - taaki galti se kabhi PC band na ho."""
    return False


def ask_user(question):
    """Sawaal poochh ke POORA jawab (text) lo - jaise "haan" / "nahi" / "thoda polite bana do".
    main.py (bol ke), jarvis.py (type karke), UI (prompt box) isko badalte hain.
    Default: None (koi jawab nahi = cancel)."""
    return None


# Aaye hue WhatsApp message jaisa private text: terminal mein mat dikhao (sirf UI + awaaz)
private_reply = False


# Is sawaal mein kaunse tools chale (naam, result) - brain.py har sawaal pe
# ise khaali karta hai. Gemini beech mein fail ho to Groq ko pata rahe ki
# kya ho chuka hai, taaki wo dobara na kare.
call_log = []


# ============================================
# DirectReply - "ye jawab seedha bolo, AI ke paas wapas mat bhejo"
#   Jaise confirmation pe "nahi" -> "Theek hai sir, cancel kar diya" turant.
#   (AI ko result bhej ke uska jawab lene mein 5-10 second lagte the.)
#   BaseException se banaya hai taaki tools ke try/except isko na pakdein aur
#   ye seedha brain.ask() tak pahunche.
# ============================================
class DirectReply(BaseException):
    def __init__(self, reply, ok=True):
        super().__init__(reply)
        self.reply = reply
        self.ok = ok          # False = kaam nahi hua (UI card "failed" dikhata hai)


# ============================================
# SAFETY LOCK
#   Khatarnak tools (shutdown, restart, lock, app band karna) aur kholne/chalane
#   wale tools tabhi chalenge jab Krish ke ABHI WALE message mein khud wo kaam
#   maanga gaya ho. AI sirf purani history dekh ke ye tools kabhi nahi chala sakta.
#   brain.ask() har message pe current_request set karta hai.
# ============================================
current_request = ""

SHUTDOWN_WORDS = {"shutdown", "shut down", "band", "bandh", "off", "power off",
                  "turn off", "switch off", "बंद", "शटडाउन"}
RESTART_WORDS = {"restart", "reboot", "रीस्टार्ट"}
LOCK_WORDS = {"lock", "लॉक"}
CLOSE_WORDS = {"close", "band", "bandh", "quit", "exit", "kill", "बंद"}
OPEN_WORDS = {"open", "kholo", "khol", "kholna", "launch", "start", "chalao", "chalu",
              "खोलो", "ओपन"}
# Memory se kuch mitana: "ye bhool jao", "birthday wali baat bhool jao"
FORGET_WORDS = {"bhool", "bhul", "bhoolo", "bhulo", "forget", "delete", "hata", "hatao",
                "mita", "mitao", "भूल", "भूलो", "हटाओ"}
# Screen dekhna: "screen pe kya hai", "is error ko samjhao", "is code mein galti batao"
SCREEN_WORDS = {"screen", "screenshot", "dekho", "dekh", "dekhkar", "error", "code", "window",
                "look", "see", "स्क्रीन", "एरर", "कोड"}

# WhatsApp / calls
MSG_WORDS = {"message", "messages", "msg", "bhejo", "bhej", "send", "reply", "whatsapp", "text",
             "likh", "likho", "bol", "keh", "bata", "मैसेज", "भेजो"}
CALL_WORDS = {"call", "phone", "dial", "milao", "lagao", "कॉल", "फोन"}
END_CALL_WORDS = {"kaat", "kat", "kaato", "cut", "end", "band", "disconnect", "hang", "rakh", "काटो"}
READ_WORDS = {"padho", "padh", "read", "sunao", "messages", "message", "msg", "dikhao", "पढ़ो"}

# Volume/mute: "chup raho" (JARVIS chup ho) pe PC mute na ho jaaye
VOLUME_WORDS = {"volume", "mute", "unmute", "awaaz", "awaz", "aawaz", "sound", "speaker",
                "आवाज़", "आवाज", "वॉल्यूम", "म्यूट"}
PLAY_WORDS = {"play", "chalao", "chala", "bajao", "baja", "sunao", "lagao", "laga",
              "चलाओ", "बजाओ", "सुनाओ", "लगाओ"}
# Media keys (play/pause/next/previous/stop): "gaana pause karo", "next gaana", "gaana roko"
MEDIA_WORDS = {"pause", "play", "next", "previous", "prev", "gaana", "gana", "gane", "song",
               "songs", "music", "track", "roko", "rok", "chalao", "चलाओ", "रोको", "गाना"}
# Volume RELATIVE badalna: "awaaz badhao", "awaaz kam karo" (set_volume/mute ke alawa)
VOLUME_REL_WORDS = {"kam", "zyada", "badhao", "badha", "badhana", "ghatao", "ghata", "tez",
                    "dheere", "increase", "decrease", "up", "down", "कम", "ज्यादा", "बढ़ाओ"}
# Screen brightness: "brightness kam karo", "roshni badhao"
BRIGHTNESS_WORDS = {"brightness", "roshni", "roshniyan", "dim", "bright",
                    "ब्राइटनेस", "रोशनी"}


def _asked_for(words):
    """True agar current_request mein in words mein se koi ho."""
    text = current_request.lower()
    tokens = set(re.findall(r"[^\s.,!?।:;]+", text))
    return any((w in text) if " " in w else (w in tokens) for w in words)


# ============================================
# @tool decorator - har tool pe lagta hai
#   1. SAFETY LOCK check (needs=... diya ho to)
#   2. UI pe 'thinking' state aur message dikhata hai
#   3. try/except - tool fail ho to crash nahi, error message AI ko jaata hai
#   4. call_log mein likhta hai ki tool chala
# ============================================
_action_ids = itertools.count(1)     # UI ke Activity panel ke liye har kaam ka alag number


def tool(message, needs=None):
    def decorator(func):
        @functools.wraps(func)     # Gemini ko asli function ka naam/docstring dikhe
        def wrapper(*args, **kwargs):
            ui.set_state("thinking")
            aid = next(_action_ids)
            # Activity panel: title = tool ka message ("Opening chrome"), detail = arguments
            try:
                values = inspect.signature(func).bind(*args, **kwargs).arguments
            except TypeError:
                values = {}
            # "Searching web: {query}..." -> title "Searching web", detail = query
            # "Opening {name}..."        -> title "Opening chrome", detail = tool ka naam
            try:
                filled = message.format(**values).rstrip(". ")
            except (KeyError, IndexError):
                filled = message.split("{")[0].rstrip(". ")
            if ":" in filled:
                title, detail = (p.strip() for p in filled.split(":", 1))
            else:
                title, detail = filled, func.__name__.replace("_", " ")
            title, detail = (title or func.__name__)[:40], detail[:60]

            # --- Safety lock: kya Krish ne abhi ye kaam maanga hai? ---
            if needs and not _asked_for(needs):
                ui.log(f"BLOCKED {func.__name__}: current message did not ask for it")
                ui.action(aid, title, "Blocked (safety lock)", "failed")
                result = (f"BLOCKED for safety: Krish's current message did not ask for "
                          f"{func.__name__}. Do NOT call it again. Just answer Krish's "
                          f"current message normally.")
                call_log.append((func.__name__, result))
                return result

            try:
                # message mein {name} jaisi jagah ho to asli value bhar do
                ui.log(message.format(**values))
            except (KeyError, IndexError):
                ui.log(title + "...")
            ui.action(aid, title, detail, "running")
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                ui.log(f"Error: {e}")
                result = f"Error while running {func.__name__}: {e}"
            except DirectReply as d:
                # Tool ne seedha jawab diya - ok=False (cancel, contact nahi mila) = failed card
                ui.action(aid, title, detail if d.ok else d.reply[:60], "done" if d.ok else "failed")
                raise
            failed = str(result).startswith(("Error", "BLOCKED", "Could not"))
            ui.action(aid, title, detail if not failed else str(result)[:60], "failed" if failed else "done")
            call_log.append((func.__name__, result))
            return result
        return wrapper
    return decorator


# ============================================
# 1. WEB SEARCH - latest info (news, score, weather, prices...)
# ============================================
@tool("Searching web: {query}...")
def web_search(query: str) -> str:
    """Search the internet for current or recent information: news, live cricket
    scores, prices, recent events, or anything you don't know or that may
    have changed after your training. Returns top results; summarise them briefly."""
    from ddgs import DDGS    # DuckDuckGo search (free, key nahi chahiye)

    results = DDGS().text(query, max_results=5)
    if not results:
        return "No results found."

    # Har result ka title + chhota description Gemini ko bhejo
    return "\n\n".join(f"{r['title']}\n{r['body']}\n({r['href']})" for r in results)


# ============================================
# 2. WEBSITE KHOLNA
# ============================================
# Common websites ke naam aur unke links
WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "instagram": "https://www.instagram.com",
    "github": "https://github.com",
    "whatsapp": "https://web.whatsapp.com",
    "gmail": "https://mail.google.com",
    "facebook": "https://www.facebook.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "linkedin": "https://www.linkedin.com",
    "chatgpt": "https://chatgpt.com",
    "gemini": "https://gemini.google.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.in",
    "flipkart": "https://www.flipkart.com",
    "spotify": "https://open.spotify.com",
}


@tool("Opening {name}...", needs=OPEN_WORDS)
def open_website(name: str) -> str:
    """Open a website in the browser. ONLY use when Krish explicitly says open/kholo -
    never just to answer a question. E.g. 'youtube', 'google', 'instagram',
    'github', 'whatsapp', 'gmail', or a domain like 'wikipedia.org'."""
    key = name.lower().replace("web", "").replace(".com", "").strip()

    if key in WEBSITES:
        url = WEBSITES[key]
    elif "." in name:                          # Domain diya hai, jaise "wikipedia.org"
        url = name if name.startswith("http") else "https://" + name
    else:                                      # Pata nahi - Google pe dhoondh lo
        url = "https://www.google.com/search?q=" + name.replace(" ", "+")

    webbrowser.open(url)
    return f"Opened {url}"


# ============================================
# 3. YOUTUBE PE GAANA/VIDEO CHALANA
# ============================================
@tool("Playing {song} on YouTube...", needs=PLAY_WORDS | OPEN_WORDS)
def play_on_youtube(song: str) -> str:
    """Play a song or video on YouTube (opens the top result and starts playing).
    ONLY use when Krish asks to play/chalao/bajao something."""
    if not song or not song.strip():
        return "Error: no song name given, ask Krish what to play"
    import pywhatkit    # Yahin import kiya kyunki ye load hone mein time leta hai
    pywhatkit.playonyt(song)
    return f"Playing '{song}' on YouTube"


# ============================================
# 4. APP KHOLNA
# ============================================
# App ka naam -> Windows command. "start" command Windows ki App list
# se bhi app dhoondh leta hai (jaise chrome, winword)
APPS = {
    "notepad": "notepad",
    "calculator": "calc",
    "calc": "calc",
    "chrome": "start chrome",
    "google chrome": "start chrome",
    "edge": "start msedge",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "file explorer": "explorer",
    "explorer": "explorer",
    "files": "explorer",
    "cmd": "start cmd",
    "command prompt": "start cmd",
    "powershell": "start powershell",
    "paint": "mspaint",
    "word": "start winword",
    "excel": "start excel",
    "powerpoint": "start powerpnt",
    "settings": "start ms-settings:",
    "task manager": "taskmgr",
    "camera": "start microsoft.windows.camera:",
    "spotify": "start spotify:",
}


def _windows_search_open(name):
    """Start menu kholke naam type karke Enter dabata hai - bilkul jaise hum
    haath se karte hain. List mein na ho aisi apps ke liye backup tareeka."""
    import pyautogui
    pyautogui.press("win")
    time.sleep(0.8)          # Start menu khulne do
    pyautogui.write(name, interval=0.05)
    time.sleep(1.2)          # Search results aane do
    pyautogui.press("enter")


@tool("Opening {name}...", needs=OPEN_WORDS)
def open_app(name: str) -> str:
    """Open a Windows application, e.g. notepad, calculator, chrome, vs code,
    file explorer, cmd, paint, word, excel, settings, task manager, spotify.
    Any other installed app is found via Windows search."""
    key = name.lower().strip()

    if key in APPS:
        # shell=True taaki "start ..." jaise Windows commands chal sakein
        subprocess.Popen(APPS[key], shell=True)
        return f"Opened {name}"

    # List mein nahi hai - Windows search se dhoondh ke kholo
    _windows_search_open(name)
    return f"'{name}' was not in the known app list, so it was searched and opened via Windows Start search."


# ============================================
# 5. APP BAND KARNA
# ============================================
# App ka naam -> uske process (.exe) ka naam
PROCESSES = {
    "notepad": ["notepad.exe"],
    "calculator": ["calculatorapp.exe", "calc.exe"],
    "calc": ["calculatorapp.exe", "calc.exe"],
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "edge": ["msedge.exe"],
    "vs code": ["code.exe"],
    "vscode": ["code.exe"],
    "visual studio code": ["code.exe"],
    "cmd": ["cmd.exe"],
    "command prompt": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "paint": ["mspaint.exe"],
    "word": ["winword.exe"],
    "excel": ["excel.exe"],
    "powerpoint": ["powerpnt.exe"],
    "task manager": ["taskmgr.exe"],
    "spotify": ["spotify.exe"],
}


@tool("Closing {name}...", needs=CLOSE_WORDS)
def close_app(name: str) -> str:
    """Close (quit) a running Windows application by name, e.g. chrome, notepad,
    calculator, vs code, file explorer, spotify."""
    key = name.lower().strip()

    # File Explorer special hai: explorer.exe band kiya to taskbar bhi gayab ho
    # jaata hai! Isliye sirf Explorer ki windows band karte hain.
    if key in ("file explorer", "explorer", "files"):
        if DRY_RUN:
            return _dry_run("close all File Explorer windows")
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        "(New-Object -ComObject Shell.Application).Windows() | ForEach-Object { $_.Quit() }"],
                       capture_output=True)
        return "Closed File Explorer windows"

    # Process ke naam: list se lo, warna "naam.exe" maan lo
    targets = PROCESSES.get(key, [key.replace(" ", "") + ".exe"])

    closed = 0
    for proc in psutil.process_iter(["name"]):
        if (proc.info["name"] or "").lower() in targets:
            if DRY_RUN:
                closed += 1          # Sirf gino, band mat karo
                continue
            try:
                proc.terminate()     # Process ko band karne ko bolo
                closed += 1
            except psutil.Error:
                pass                 # Koi process band na ho to chhod do

    if closed == 0:
        return f"{name} is not running (or could not be found)."
    if DRY_RUN:
        return _dry_run(f"close {closed} process(es) of {name} ({', '.join(targets)})")
    return f"Closed {name}"


# ============================================
# 6. TIME AUR DATE
# ============================================
@tool("Checking time...")
def get_time_date() -> str:
    """Get the current local time, date and day of the week."""
    now = datetime.datetime.now()
    return now.strftime("Time: %I:%M %p, Date: %d %B %Y, Day: %A")


# ============================================
# 7. SYSTEM INFO - battery, CPU, RAM
# ============================================
@tool("Checking system status...")
def system_info() -> str:
    """Get the computer's battery level and charging status, CPU usage and RAM usage."""
    cpu = psutil.cpu_percent(interval=0.5)         # Aadha second naap ke CPU %
    ram = psutil.virtual_memory()
    info = (f"CPU usage: {cpu}%. RAM used: {ram.percent}% "
            f"({ram.used / 1e9:.1f} GB of {ram.total / 1e9:.1f} GB).")

    battery = psutil.sensors_battery()             # Desktop PC pe None hota hai
    if battery:
        charging = "charging" if battery.power_plugged else "not charging"
        info += f" Battery: {battery.percent}% ({charging})."
    else:
        info += " No battery (desktop PC)."
    return info


# ============================================
# 8. SCREENSHOT
# ============================================
def _pictures_folder():
    """Pictures folder ka asli rasta (OneDrive pe ho tab bhi sahi milta hai)."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        path = os.path.expandvars(winreg.QueryValueEx(key, "My Pictures")[0])
        if os.path.isdir(path):
            return path
    except OSError:
        pass
    return os.path.join(os.path.expanduser("~"), "Pictures")


@tool("Taking screenshot...")
def take_screenshot() -> str:
    """Take a screenshot of the whole screen and save it in the Pictures folder."""
    from PIL import ImageGrab    # Pillow library - screen ki photo leta hai

    name = datetime.datetime.now().strftime("JARVIS_Screenshot_%Y%m%d_%H%M%S.png")
    path = os.path.join(_pictures_folder(), name)
    ImageGrab.grab(all_screens=True).save(path)
    return f"Screenshot saved: {path}"


# ============================================
# 9. VOLUME (pycaw)
# ============================================
def _speaker_volume():
    """Windows ke speaker ka volume control deta hai."""
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume


@tool("Setting volume to {level}%...", needs=VOLUME_WORDS)
def set_volume(level: int) -> str:
    """Set the system (speaker) volume to a level from 0 to 100 percent."""
    level = max(0, min(100, int(level)))           # 0 se 100 ke beech rakho
    volume = _speaker_volume()
    volume.SetMute(0, None)                        # Volume badhaya hai to unmute bhi karo
    volume.SetMasterVolumeLevelScalar(level / 100, None)   # pycaw 0.0-1.0 leta hai
    return f"Volume set to {level}%"


@tool("Changing mute...", needs=VOLUME_WORDS)
def set_mute(mute: bool) -> str:
    """Mute (mute=True) or unmute (mute=False) the system speakers."""
    _speaker_volume().SetMute(1 if mute else 0, None)
    return "Muted" if mute else "Unmuted"


# ============================================
# 9b. VOLUME RELATIVE - "awaaz badhao" / "awaaz kam karo"
#   set_volume se alag: ye abhi ka level padh ke upar-neeche 10% (ya jitna bolo) le jaata hai
# ============================================
@tool("Changing volume {direction}...", needs=VOLUME_WORDS | VOLUME_REL_WORDS)
def volume_change(direction: str, amount: int = 10) -> str:
    """Turn the current speaker volume UP or DOWN by a few percent (default 10) - use for
    'awaaz badhao' / 'awaaz kam karo' / 'volume up' / 'thoda dheere'. direction = 'up' or
    'down', amount = how many percent. To set an exact level use set_volume instead."""
    step = str(direction or "").strip().lower()
    if step not in ("up", "down"):
        return "Could not change volume: direction must be 'up' or 'down'."
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return "Could not change volume: amount must be a number of percent."
    amount = max(1, min(100, amount))
    if DRY_RUN:
        return _dry_run(f"volume {step} by {amount}% (abhi ka level padh ke upar-neeche le jaata)")
    volume = _speaker_volume()
    current = int(round(volume.GetMasterVolumeLevelScalar() * 100))
    target = max(0, min(100, current + (amount if step == "up" else -amount)))
    volume.SetMute(0, None)                               # Badha rahe hain to pehle unmute karo
    volume.SetMasterVolumeLevelScalar(target / 100, None)
    return f"Volume {step} by {amount}%: {current}% -> {target}%"


# ============================================
# 9c. MEDIA KEYS - play/pause, next, previous, stop
#   Windows ke media keys (VK 0xB3/0xB0/0xB1/0xB2) - koi app chalu ho ya na ho,
#   khud chal raha player (Spotify/Chrome/YouTube) pakad leta hai. Koi naya library nahi.
# ============================================
MEDIA_KEYS = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2}
_MEDIA_ALIASES = {"play": "play_pause", "pause": "play_pause", "resume": "play_pause",
                  "toggle": "play_pause", "prev": "previous", "back": "previous",
                  "skip": "next", "forward": "next", "pause_play": "play_pause"}


def _media_key(vk):
    """Windows media key dabao aur chhod do (keybd_event: pehle press, phir KEYUP)."""
    import ctypes
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)              # press
    ctypes.windll.user32.keybd_event(vk, 0, 0x0002, 0)          # release (KEYEVENTF_KEYUP)


@tool("Media: {action}...", needs=MEDIA_WORDS)
def media_control(action: str) -> str:
    """Control music/video playback with the Windows media keys. action = 'play_pause'
    (pause or resume - for 'gaana pause karo', 'chalao'), 'next' (next song/track),
    'previous' (previous song/track) or 'stop'. Use only when Krish's current message asks
    to play, pause, skip or stop the music - it works with whatever player is running."""
    key = str(action or "").strip().lower().replace("-", "_").replace(" ", "_")
    key = _MEDIA_ALIASES.get(key, key)
    if key not in MEDIA_KEYS:
        return "Could not control media: use play_pause, next, previous or stop."
    if DRY_RUN:
        return _dry_run(f"press media key {key} (VK 0x{MEDIA_KEYS[key]:02X})")
    _media_key(MEDIA_KEYS[key])
    return f"Media key sent: {key.replace('_', ' ')}"


# ============================================
# 9d. SCREEN BRIGHTNESS - sirf laptop ki apni screen (WMI se, nayi library nahi)
#   Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods
#   WmiGetBrightness() se padhte hain, WmiSetBrightness se badalte hain.
#   External monitor / desktop PC pe ye class hoti hi nahi - saaf error, crash nahi.
# ============================================
_NO_BRIGHTNESS = ("Could not control screen brightness: ye sirf laptop ki apni built-in screen "
                  "pe chalta hai, is PC pe brightness control nahi mila (external monitor ho "
                  "sakta hai).")
_BRIGHTNESS_HEAD = "Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods"


def _brightness_read():
    """Laptop screen ka current brightness (0-100). Na mile / error ho to None."""
    # Padhna WmiMonitorBrightness.CurrentBrightness se hota hai (Methods class mein get method hai hi nahi)
    ps = ("$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | "
          "Where-Object Active | Select-Object -First 1; "
          "if ($m) { $m.CurrentBrightness } else { 'NONE' }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=25).stdout.strip()
        return None if out in ("", "NONE") else int(out)
    except (subprocess.SubprocessError, OSError, ValueError):
        return None


_NO_READ = ("Could not read the current brightness, so up/down is not possible. "
            "Ask Krish to say a number, like 'brightness 50 karo'.")


def _brightness_apply(target):
    """Write karo, phir wapas padh ke verify karo. Return: (ok, asli level ya None, likha gaya?)."""
    if not _brightness_write(target):
        return False, None, False
    time.sleep(0.4)                                  # panel ko badalne do
    now = _brightness_read()
    return (now is not None and abs(now - target) <= 2), now, True


def _brightness_verdict(ok, now, wrote, target, before=None):
    """Verify ke baad jawab: "kar diya" sirf tab jab screen ne sach mein wo level dikhaya."""
    if not wrote:
        return _NO_BRIGHTNESS
    if not ok:
        return (f"Could not verify brightness change: asked {target}%, "
                f"screen reads {now if now is not None else 'unknown'}%.")
    return f"Screen brightness {before}% -> {now}%." if before is not None else f"Screen brightness {now}% set."


def _brightness_write(level):
    """Brightness 0-100 set karo. False = ye screen brightness control nahi kar sakti."""
    ps = (f"$m = {_BRIGHTNESS_HEAD}; if ($m) {{ $m | Invoke-CimMethod -MethodName "
          f"WmiSetBrightness -Arguments @{{Timeout=1;Brightness={int(level)}}} | Out-Null; 'OK' }} "
          f"else {{ 'NONE' }}")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=25).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return False
    return out.endswith("OK")


@tool("Brightness: {action}...", needs=BRIGHTNESS_WORDS)
def brightness(action: str, level: int = None) -> str:
    """Get or change the laptop's built-in screen brightness (0-100 percent).
    action = 'get' (current brightness), 'set' (needs level, e.g. 50), 'up' or 'down'
    (10% step). Use for 'brightness kam karo', 'roshni zyada karo', 'brightness 50 karo'.
    It only works on a laptop's own screen - on an external monitor it changes nothing."""
    act = str(action or "").strip().lower()
    if act not in ("get", "set", "up", "down"):
        return "Could not control brightness: action must be get, set, up or down."

    if act == "set":
        try:
            target = max(0, min(100, int(level)))
        except (TypeError, ValueError):
            return "Could not set brightness: level must be a number from 0 to 100."
        if DRY_RUN:
            return _dry_run(f"set screen brightness to {target}%")
        ok, now, wrote = _brightness_apply(target)
        return _brightness_verdict(ok, now, wrote, target)

    if act in ("up", "down"):
        step = 10                                    # 10% ka step
        if DRY_RUN:
            return _dry_run(f"screen brightness {'+' if act == 'up' else '-'} {step}%")
        current = _brightness_read()
        if current is None:
            return _NO_READ
        target = max(0, min(100, current + (step if act == "up" else -step)))
        ok, now, wrote = _brightness_apply(target)
        return _brightness_verdict(ok, now, wrote, target, before=current)

    # action == "get": sirf padhna hai (kuch badalta nahi) - DRY_RUN mein bhi chalega
    current = _brightness_read()
    return f"Screen brightness {current}%." if current is not None else _NO_BRIGHTNESS


# ============================================
# 9b. FILES - naam se dhoondho aur kholo (sirf padhna + default app mein kholna)
#   Sirf 4 folder: Documents, Downloads, Desktop, Pictures. File ka content kabhi
#   nahi padhte; delete / edit / move / rename koi tool nahi hai.
# ============================================
FIND_WORDS = {"find", "search", "dhoondo", "dhundo", "dhoondh", "dhundh", "dikhao", "file", "files",
              "latest", "naya", "nayi", "newest", "recent", "open", "kholo", "khol", "chalao"}
FILE_OPEN_WORDS = {"open", "kholo", "khol", "kholna", "chalao", "launch", "start"}
_SHELL_FOLDER_KEYS = {"documents": "Personal", "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
                      "desktop": "Desktop", "pictures": "My Pictures"}
_FILE_TYPES = {"pdf": {".pdf"}, "word": {".doc", ".docx"}, "excel": {".xls", ".xlsx", ".csv"},
               "ppt": {".ppt", ".pptx"}, "powerpoint": {".ppt", ".pptx"},
               "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"},
               "photo": {".jpg", ".jpeg", ".png", ".webp"}, "video": {".mp4", ".mkv", ".avi", ".mov"},
               "zip": {".zip", ".rar", ".7z"}, "txt": {".txt"}, "text": {".txt"}}
_LATEST_TOKENS = {"latest", "naya", "nayi", "newest", "recent", "sabse", "last"}
_FILLER_TOKENS = {"file", "files", "ka", "ki", "ke", "wali", "wala", "mein", "me", "se", "folder",
                  "the", "my", "in", "from", "mera", "meri", "mere", "dhoondo", "dhundo", "find",
                  "search", "open", "kholo", "khol", "do", "karo", "for", "a"}
# Ye extension default app mein kholne pe program CHALA dete hain - kabhi nahi kholte
_RUNNABLE_EXT = {".exe", ".bat", ".cmd", ".ps1", ".msi", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".lnk",
                 ".scr", ".com", ".reg", ".hta", ".jar", ".py", ".pyw", ".dll", ".cpl", ".msc"}
_ORDINALS = {"1": 1, "pehla": 1, "pehli": 1, "first": 1, "1st": 1, "ek": 1,
             "2": 2, "dusra": 2, "dusri": 2, "doosra": 2, "doosri": 2, "second": 2, "2nd": 2,
             "3": 3, "teesra": 3, "teesri": 3, "third": 3, "3rd": 3, "teen": 3,
             "4": 4, "chautha": 4, "chauthi": 4, "fourth": 4, "4th": 4, "char": 4,
             "5": 5, "paanchwa": 5, "paanchvi": 5, "fifth": 5, "5th": 5, "paanch": 5,
             "6": 6, "sixth": 6, "7": 7, "seventh": 7, "8": 8, "eighth": 8}
last_files = []          # pichle find_files ke poore rasta (sirf RAM mein)
MAX_FILE_RESULTS = 8
_MAX_SCAN = 20000        # itni entries se zyada nahi dekhte (tez rehne ke liye)
_MAX_DEPTH = 4


def _known_folder(name):
    """Documents/Downloads/Desktop/Pictures ka asli rasta (OneDrive pe ho tab bhi sahi)."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        path = os.path.expandvars(winreg.QueryValueEx(key, _SHELL_FOLDER_KEYS[name])[0])
        if os.path.isdir(path):
            return os.path.normpath(path)
    except OSError:
        pass
    path = os.path.join(os.path.expanduser("~"), name.capitalize())
    return os.path.normpath(path) if os.path.isdir(path) else None


def _allowed_folders():
    """{naam: rasta} - sirf jo folder sach mein hain."""
    found = {n: _known_folder(n) for n in _SHELL_FOLDER_KEYS}
    return {n: p for n, p in found.items() if p}


def _inside_allowed(path):
    """True agar path in 4 folder mein se kisi ke andar ki asli file hai (.. ya shortcut se bahar nahi)."""
    real = os.path.normcase(os.path.realpath(path))
    for folder in _allowed_folders().values():
        base = os.path.normcase(os.path.realpath(folder))
        if real.startswith(base + os.sep):
            return True
    return False


def _folder_name(token):
    """'downloads' / 'download' -> 'downloads'; folder ka naam nahi to None."""
    for name in _SHELL_FOLDER_KEYS:
        if token in (name, name.rstrip("s")):
            return name
    return None


def _parse_file_query(query):
    """query -> (folders, extensions, latest, naam ke shabd). Content kabhi nahi dekhte."""
    tokens = re.findall(r"[\w.]+", str(query or "").lower())
    folders, exts, latest, words = [], set(), False, []
    for t in tokens:
        if _folder_name(t):
            folders.append(_folder_name(t))
        elif t in _FILE_TYPES:
            exts |= _FILE_TYPES[t]
        elif t in _LATEST_TOKENS:
            latest = True
        elif t not in _FILLER_TOKENS:
            words.append(t)
    return folders, exts, latest, words


@tool("Finding files: {query}...", needs=FIND_WORDS)
def find_files(query: str) -> str:
    """Find files by NAME in the user's Documents, Downloads, Desktop and Pictures folders only.
    query = words like 'resume', 'latest pdf downloads', 'invoice pdf'. Newest files come first.
    Returns at most 8 numbered results (name, folder, date). Never reads file content.
    Afterwards use open_file to open one."""
    global last_files
    folders, exts, latest, words = _parse_file_query(query)
    roots = _allowed_folders()
    chosen = {n: roots[n] for n in folders if n in roots} or roots
    if not chosen:
        return "Error: Documents/Downloads/Desktop/Pictures folders not found"
    if not (words or exts or latest):
        return "Could not search: tell me a file name, a type like pdf, or say 'latest'."
    hits, scanned = [], 0
    skip = {"node_modules", ".git", "__pycache__", "appdata"}
    for label, root in chosen.items():
        stack = [(root, 0)]
        while stack and scanned < _MAX_SCAN:
            folder, depth = stack.pop()
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for e in entries:
                scanned += 1
                try:
                    if e.is_dir(follow_symlinks=False):
                        if depth < _MAX_DEPTH and not e.name.startswith(".") and e.name.lower() not in skip:
                            stack.append((e.path, depth + 1))
                        continue
                    if not e.is_file(follow_symlinks=False) or e.name.startswith((".", "~$")):
                        continue
                    name = e.name.lower()
                    if exts and os.path.splitext(name)[1] not in exts:
                        continue
                    if words and not all(w in name for w in words):
                        continue
                    hits.append((e.stat().st_mtime, e.path, label))
                except OSError:
                    continue
    hits.sort(key=lambda h: h[0], reverse=True)      # Sabse naya pehle
    hits = hits[:MAX_FILE_RESULTS]
    last_files = [h[1] for h in hits]
    if not hits:
        return "No matching files found in Documents, Downloads, Desktop, Pictures."
    lines = [f"{i}. {os.path.basename(path)} ({label}, "
             f"{datetime.datetime.fromtimestamp(m).strftime('%d %b %Y')})"
             for i, (m, path, label) in enumerate(hits, 1)]
    return f"Found {len(hits)} file(s):\n" + "\n".join(lines)


@tool("Opening file: {which}...", needs=FILE_OPEN_WORDS)
def open_file(which: str) -> str:
    """Open a file from the LAST find_files result in its default app. which = the result number
    ('1', 'pehli', 'second') or part of the file name. Only files inside Documents, Downloads,
    Desktop or Pictures; programs/scripts are never opened. Cannot delete, edit, move or rename."""
    key = str(which or "").strip().lower()
    if not last_files:
        return "Could not open: no file list yet. Use find_files first."
    path = None
    n = _ORDINALS.get(key)
    if n is None and re.fullmatch(r"\d{1,2}", key):
        n = int(key)
    if n is not None:
        if 1 <= n <= len(last_files):
            path = last_files[n - 1]
    else:
        parts = [w for w in re.findall(r"[\w.]+", key) if w not in _FILLER_TOKENS]
        matches = [f for f in last_files if parts and all(w in os.path.basename(f).lower() for w in parts)]
        if len(matches) == 1:
            path = matches[0]
        elif len(matches) > 1:
            return "Could not open: more than one match, ask Krish for the number."
    if not path:
        return "Could not open: that file is not in the last search results."
    if not os.path.isfile(path) or not _inside_allowed(path):
        return "Could not open: file is missing or outside Documents/Downloads/Desktop/Pictures."
    if os.path.splitext(path)[1].lower() in _RUNNABLE_EXT:
        return "Could not open: programs and scripts are never opened by JARVIS."
    if DRY_RUN:
        return _dry_run(f"open file {os.path.basename(path)}")
    os.startfile(path)
    return f"Opened {os.path.basename(path)}"


# ============================================
# 9c. NOTES - "note likho: kal Rahul se milna hai", "mere notes padho", "note 2 hata do"
#   notes.json mein (gitignore hai). PRIVACY: note ka text terminal/log mein kabhi nahi
#   chhapta (tool ka message/card mein text nahi, jawab private_reply se) - sirf awaaz + HUD.
#   Note numbers poori list ke hain (1 = sabse purana), "padho" aakhri 5 dikhata hai.
# ============================================
NOTE_ADD_WORDS = {"note", "notes", "likho", "likh", "yaad"}
NOTE_LIST_WORDS = {"note", "notes", "padho", "padh", "sunao", "dikhao", "batao", "read"}
NOTE_DELETE_WORDS = {"note", "notes", "hata", "hatao", "delete", "remove", "mita", "mitao"}
NOTES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes.json")
MAX_NOTE_CHARS = 500
# "Note likho: ..." jaisa command - text chhupane ke liye (main.py / voice.py isse pehchante hain)
NOTE_ADD_RX = re.compile(r"^\s*(?:(?:hey\s+)?jarvis[\s,]+)?(?:(?:ye|is|ek|a)\s+)?"
                         r"(?:(?:note|notes)\s+(?:likho|likh do|likh lo|add karo|save karo)|"
                         r"(?:take|add|make)\s+a\s+note(?:\s+that)?|note\s+down)\s*[:,\-]?\s*(?P<t>.+?)\s*$",
                         re.IGNORECASE | re.DOTALL)


def mask_private(text):
    """Terminal/log ke liye: note likhwane wale command ka text chhupa do, baaki jaisa hai waisa."""
    return "(note likhwa rahe hain - text chhupa hai)" if NOTE_ADD_RX.match(str(text or "")) else text


def _notes_load():
    """notes.json padho. File na ho to []. Kharab ho to error (overwrite nahi - notes na jayein)."""
    try:
        with open(NOTES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        raise ValueError("notes.json kharab ho gayi hai - VS Code mein theek karo")


def _notes_save(notes):
    """Pehle temp file mein likho, phir badlo - beech mein band ho to bhi purane notes bache rahein."""
    tmp = NOTES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)
    os.replace(tmp, NOTES_FILE)


@tool("Saving note...", needs=NOTE_ADD_WORDS)
def note_add(text: str) -> str:
    """Save a short note for Krish (into notes.json) and read it back. ONLY use when Krish clearly
    asks to write/save a note ('note likho', 'note kar lo', 'take a note'). text = the note itself."""
    global private_reply
    text = " ".join(str(text or "").split())[:MAX_NOTE_CHARS]
    if not text:
        return "Could not save note: the note text is empty."
    notes = _notes_load()
    notes.append({"text": text, "time": datetime.datetime.now().strftime("%d %b %Y %H:%M")})
    _notes_save(notes)
    private_reply = True       # Note ka text terminal mein nahi dikhega
    raise DirectReply(f"Note likh liya: {text}.")


@tool("Reading notes...", needs=NOTE_LIST_WORDS)
def notes_list() -> str:
    """Read out Krish's last 5 saved notes (with their numbers). Use for 'mere notes padho'."""
    global private_reply
    notes = _notes_load()
    if not notes:
        raise DirectReply("Sir, abhi koi note save nahi hai.")
    start = max(0, len(notes) - 5)
    parts = [f"Note {i}: {n['text']}" for i, n in enumerate(notes[start:], start + 1)]
    private_reply = True       # Note ka text terminal mein nahi dikhega
    head = f"Sir, aapke {len(notes)} notes hain" + (", aakhri 5 ye hain. " if len(notes) > 5 else ". ")
    raise DirectReply(head + ". ".join(parts) + ".")


@tool("Deleting note {number}...", needs=NOTE_DELETE_WORDS)
def note_delete(number: int) -> str:
    """Delete one saved note by its number (as read out by notes_list). Asks Krish to confirm first."""
    notes = _notes_load()
    try:
        n = int(number)
    except (TypeError, ValueError):
        return "Could not delete note: the note number must be a number."
    if not 1 <= n <= len(notes):
        return f"Could not delete note: there is no note number {n} (Krish has {len(notes)} notes)."
    if not confirm(f"Sir, note {n} hata doon?"):        # Confirm ke baad hi (text sawaal mein nahi)
        raise DirectReply("Theek hai sir, note nahi hataya.")
    notes.pop(n - 1)
    _notes_save(notes)
    raise DirectReply(f"Note {n} hata diya, sir.")


# ============================================
# 9d. REMINDERS / TASKS (scheduler.py) - "10 minute baad yaad dilana ki paani peena hai"
#   Save se pehle read-back + "Sahi hai?" (haan pe hi save). Time samajh na aaye to poochta hai.
#   Reminder ka text private (terminal mein nahi). Confirm-level kaam (WhatsApp, call) reminder
#   ke saath ho to bhi us waqt main.py Krish se poochta hai - khud kabhi nahi.
# ============================================
REMIND_WORDS = {"yaad", "remind", "reminder", "dilana", "dilao", "dila", "baad", "baje", "kal", "parso",
                "roz", "har", "subah", "shaam", "raat", "schedule", "am", "pm"}
TASK_LIST_WORDS = {"task", "tasks", "reminder", "reminders", "dikhao", "batao", "padho", "list", "sunao"}
TASK_DELETE_WORDS = {"task", "tasks", "reminder", "reminders", "hata", "hatao", "mita", "delete",
                     "cancel", "clear"}
SNOOZE_WORDS = {"snooze", "phir", "baad"}
_YES = {"haan", "han", "ha", "haa", "yes", "yeah", "sahi", "theek", "ok", "okay", "ji", "bilkul", "pakka",
        "kar", "karo", "do", "sure", "correct", "right"}
_NO = {"nahi", "nahin", "no", "mat", "galat", "cancel", "nope", "wrong"}


def _said_yes(answer):
    """ask_user ka jawab haan hai? (jawab na mile = nahi)"""
    words = set(re.findall(r"[^\s.,!?।]+", str(answer or "").lower()))
    return bool(words & _YES) and not words & _NO


@tool("Setting reminder...", needs=REMIND_WORDS)
def reminder_add(request: str) -> str:
    """Create a reminder or scheduled task from Krish's sentence, e.g. '10 minute baad yaad dilana ki
    paani peena hai', 'kal subah 7 baje weather batana', 'har roz raat 10 baje sone ki yaad dilana'.
    request = his full sentence as spoken. It asks him to confirm before saving and asks again if
    the time is unclear - never guess a time."""
    global private_reply
    import scheduler
    status = scheduler.parse_request(request)
    if status[0] == "ask":                                # Time/kaam adhoora - poochho, andaza nahi
        answer = ask_user(status[1])
        if not answer:
            raise DirectReply("Theek hai sir, reminder nahi banaya.", ok=False)
        status = scheduler.parse_request(f"{request} {answer}")
    if status[0] != "ok":
        raise DirectReply("Sir, time samajh nahi aaya. '10 minute baad' ya 'kal subah 7 baje' jaise "
                          "bolke dobara batayein.", ok=False)
    task = status[1]
    private_reply = True       # Reminder ka text terminal mein nahi dikhega (sawaal mein bhi text hai)
    answer = ask_user(f"{task['label'].capitalize()}: {task['what']}. Sahi hai?")
    if not _said_yes(answer):
        private_reply = False
        raise DirectReply("Theek hai sir, reminder nahi banaya.", ok=False)
    scheduler.add(task["when"], task["what"], task["repeat"], task["kind"])
    raise DirectReply(f"Reminder set: {task['label']}, {task['what']}.")


@tool("Reading tasks...", needs=TASK_LIST_WORDS)
def task_list() -> str:
    """Read out Krish's saved reminders/tasks with their numbers ('meri tasks dikhao')."""
    global private_reply
    import scheduler
    tasks = scheduler.all_tasks()
    if not tasks:
        raise DirectReply("Sir, abhi koi task ya reminder save nahi hai.")
    private_reply = True
    parts = [f"Task {i}: {scheduler.describe(t)}" for i, t in enumerate(tasks[:8], 1)]
    raise DirectReply(f"Sir, {len(tasks)} tasks hain. " + ". ".join(parts) + ".")


@tool("Deleting task {number}...", needs=TASK_DELETE_WORDS)
def task_delete(number: int) -> str:
    """Delete one reminder/task by its number (as read out by task_list). Asks Krish to confirm first."""
    import scheduler
    try:
        n = int(number)
    except (TypeError, ValueError):
        return "Could not delete task: the number must be a number."
    if not 1 <= n <= len(scheduler.all_tasks()):
        return f"Could not delete task: there is no task number {n}."
    if not confirm(f"Sir, task {n} hata doon?"):
        raise DirectReply("Theek hai sir, task nahi hataya.")
    scheduler.remove_number(n)
    raise DirectReply(f"Task {n} hata diya, sir.")


@tool("Clearing all reminders...", needs=TASK_DELETE_WORDS)
def tasks_clear() -> str:
    """Delete ALL reminders/tasks ('sab reminders hata do'). Asks Krish to confirm first."""
    import scheduler
    count = len(scheduler.all_tasks())
    if not count:
        raise DirectReply("Sir, koi task hai hi nahi.")
    if not confirm(f"Sir, saare {count} reminders hata doon?"):
        raise DirectReply("Theek hai sir, kuch nahi hataya.")
    scheduler.clear()
    raise DirectReply("Saare reminders hata diye, sir.")


@tool("Snoozing reminder...", needs=SNOOZE_WORDS)
def reminder_snooze(minutes: int = 10) -> str:
    """Snooze the reminder that just went off: remind Krish again after `minutes` (default 10).
    Use for 'snooze 10 minute'."""
    import scheduler
    try:
        mins = max(1, min(720, int(minutes)))
    except (TypeError, ValueError):
        mins = 10
    if not scheduler.snooze(mins):
        raise DirectReply("Sir, abhi koi reminder baja nahi jo snooze karun.", ok=False)
    raise DirectReply(f"Theek hai sir, {mins} minute baad phir yaad dilaunga.")


# ============================================
# 9e. CONTENT CREATOR PACK - caption, hashtags, reel script, YouTube title/description, hooks
#   Likhne ka kaam brain.generate_text() karta hai (Gemini pehle, phir Groq - model .env se).
#   Chhota jawab bolte hain; lamba (script/description/hashtags) poora HUD mein, bolne mein
#   sirf pehli line. "copy kar do" = aakhri jawab clipboard mein (confirm ke baad).
# ============================================
CONTENT_WORDS = {"caption", "captions", "script", "hashtag", "hashtags", "title", "description",
                 "hook", "hooks", "likho", "likh", "do", "suggest", "idea", "ideas", "batao", "banao"}
COPY_WORDS = {"copy", "clipboard"}
CONTENT_KINDS = {
    "caption": ("Instagram/Reels caption", "Write 3 different caption options. Each 1-2 short lines, "
                "catchy, with 1-2 fitting emojis. Number them 1., 2., 3."),
    "hashtags": ("hashtags", "Write {n} relevant hashtags (mix of popular and niche), all on ONE line "
                 "separated by spaces, each starting with #. Nothing else."),
    "reel_script": ("Reels/Shorts script", "Write a {sec}-second spoken script: first line = a strong hook, "
                    "then short lines Krish can speak, last line = a call to action. One line per beat, "
                    "about {words} words in total. No stage directions in brackets."),
    "youtube_title": ("YouTube title", "Write 3 different title options, each under 70 characters, "
                      "curiosity-driven but honest, no clickbait lies. Number them 1., 2., 3."),
    "youtube_description": ("YouTube description", "Write one description: 2-3 short lines about the "
                            "video, then a line asking to like/subscribe, then 3-5 hashtags."),
    "hook_ideas": ("video hooks", "Write 3 different opening hook lines (first 3 seconds of the video), "
                   "each one short and punchy. Number them 1., 2., 3."),
}
_LONG_KINDS = {"reel_script", "youtube_description", "hashtags"}
last_content = ""      # Aakhri likha hua poora jawab (RAM) - "copy kar do" isi ko copy karta hai


def _content_style():
    """memory.json se Krish ki content style ('meri style casual rakhna') - na ho to ''."""
    try:
        import memory
        facts = [f for f in memory.all_facts() if "style" in f.lower()]
    except Exception:
        return ""
    return " ".join(facts)


@tool("Writing {kind}...", needs=CONTENT_WORDS)
def content_help(kind: str, topic: str) -> str:
    """Write content for Krish's social media. kind = one of: caption, hashtags, reel_script,
    youtube_title, youtube_description, hook_ideas. topic = what the content is about (e.g. 'Diwali reel',
    'Python JARVIS project'). Use when Krish asks for a caption, hashtags, reel script, YouTube title or
    description, or hook ideas. The answer is shown/spoken to Krish directly, do not repeat it."""
    global last_content
    import brain
    key = str(kind or "").strip().lower().replace(" ", "_")
    key = {"hashtag": "hashtags", "script": "reel_script", "title": "youtube_title",
           "description": "youtube_description", "hooks": "hook_ideas", "hook": "hook_ideas"}.get(key, key)
    if key not in CONTENT_KINDS:
        return f"Could not write content: kind must be one of {', '.join(CONTENT_KINDS)}."
    topic = " ".join(str(topic or "").split())
    if not topic:
        return "Could not write content: the topic is empty, ask Krish what it is about."

    req = current_request.lower()
    english = "english" in req or "अंग्रेज" in req
    m = re.search(r"(\d{1,3})\s*(?:second|sec|s\b)", req)
    seconds = min(int(m[1]), 180) if m else 30
    m = re.search(r"(\d{1,2})\s*hashtag", req)
    count = min(int(m[1]), 30) if m else 10
    label, rule = CONTENT_KINDS[key]
    rule = rule.format(n=count, sec=seconds, words=int(seconds * 2.5))
    style = _content_style()
    prompt = (f"You are a social media content writer for Krish, an Indian tech creator.\n"
              f"Task: {label} about: {topic}\n{rule}\n"
              f"Language: {'English' if english else 'Roman Hinglish (Hindi written in English letters, never Devanagari)'}.\n"
              + (f"Krish's style notes: {style}\n" if style else "")
              + "Plain text only: no markdown, no ** or #-headings, no intro or explanation, just the content.")
    text = brain.generate_text(prompt)
    if not text:
        return "Error: could not write the content right now (AI not answering). Try again in a minute."
    # Har line saaf karo (hashtag wali line nahi: _tidy line ke shuru ka # hata deta hai)
    text = "\n".join(line.strip() if not line.strip() or line.lstrip().startswith("#") else brain._tidy(line)
                     for line in text.strip().splitlines()).strip()
    last_content = text

    lines = [l for l in text.splitlines() if l.strip()]
    if key in _LONG_KINDS or len(text) > 350:
        ui.add_message("ai", text)                  # Poora text HUD mein
        first = lines[0] if key != "hashtags" else " ".join(lines[0].split()[:3])
        raise DirectReply(f"{first} ... baaki screen pe hai, sir. 'Copy kar do' bolo to clipboard mein daal dunga.")
    raise DirectReply(text + "\nCopy chahiye to 'copy kar do' boliye.")


def _set_clipboard(text):
    """Windows clipboard mein text (ctypes se, koi library nahi). True = ho gaya."""
    import ctypes
    from ctypes import wintypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.GlobalAlloc.restype = wintypes.HGLOBAL
    k32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    u32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    data = (text + "\0").encode("utf-16-le")
    for _ in range(10):                       # Clipboard kabhi kisi aur ke paas hota hai - thoda ruk ke phir try
        if u32.OpenClipboard(None):
            break
        time.sleep(0.1)
    else:
        return False
    try:
        u32.EmptyClipboard()
        handle = k32.GlobalAlloc(0x0002, len(data))          # GMEM_MOVEABLE
        if not handle:
            return False
        ptr = k32.GlobalLock(handle)
        ctypes.memmove(ptr, data, len(data))
        k32.GlobalUnlock(handle)
        return bool(u32.SetClipboardData(13, handle))        # CF_UNICODETEXT (ab clipboard ka maalik)
    finally:
        u32.CloseClipboard()


def _get_clipboard():
    """Clipboard ka text (test mein purana wapas rakhne ke liye). Na ho to None."""
    import ctypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    u32.GetClipboardData.restype = ctypes.c_void_p
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    if not u32.OpenClipboard(None):
        return None
    try:
        h = u32.GetClipboardData(13)
        if not h:
            return None
        p = k32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


@tool("Copying to clipboard...", needs=COPY_WORDS)
def copy_last_content() -> str:
    """Copy the last content written by content_help (caption, script, hashtags...) to the Windows
    clipboard. Use only when Krish says 'copy kar do'. Asks Krish to confirm first."""
    if not last_content:
        raise DirectReply("Sir, abhi copy karne ke liye kuch likha hi nahi hai.", ok=False)
    if not confirm("Sir, clipboard mein copy kar doon?"):
        raise DirectReply("Theek hai sir, copy nahi kiya.")
    if DRY_RUN:
        _dry_run(f"copy {len(last_content)} characters to clipboard")
        raise DirectReply("Test mode hai sir, isliye clipboard mein sach mein copy nahi hua.")
    if not _set_clipboard(last_content):
        return "Error: clipboard busy or not available, could not copy."
    raise DirectReply("Copy ho gaya, sir. Ab paste kar sakte hain.")


# --- Video editors: CapCut / DaVinci Resolve / Premiere Pro (jo installed ho) ---
_EDITORS = {
    "capcut": ("CapCut", ["%LOCALAPPDATA%\\CapCut\\Apps\\CapCut.exe", "%LOCALAPPDATA%\\CapCut\\Apps\\*\\CapCut.exe",
                          "%PROGRAMFILES%\\CapCut\\CapCut.exe"], "capcut"),
    "davinci": ("DaVinci Resolve", ["%PROGRAMFILES%\\Blackmagic Design\\DaVinci Resolve\\Resolve.exe"], "resolve"),   # "DaVinci Control Panels" jaisa nahi
    "premiere": ("Premiere Pro", ["%PROGRAMFILES%\\Adobe\\Adobe Premiere Pro *\\Adobe Premiere Pro.exe"], "premiere"),
}


def _find_editor(key):
    """Editor ka rasta: pehle jaani-pehchani jagah, phir Start Menu ke shortcut. Na mile to None."""
    import glob
    _, paths, word = _EDITORS[key]
    for pattern in paths:
        found = sorted(glob.glob(os.path.expandvars(pattern)))
        if found:
            return found[-1]
    for base in (os.path.expandvars("%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs"),
                 os.path.expandvars("%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs")):
        for root, _, files in os.walk(base):
            for f in files:
                if f.lower().endswith(".lnk") and word in f.lower():
                    return os.path.join(root, f)
    return None


@tool("Opening video editor: {name}...", needs=OPEN_WORDS)
def open_editor(name: str) -> str:
    """Open a video editor: 'capcut', 'davinci' (DaVinci Resolve) or 'premiere' (Premiere Pro),
    only if it is installed. Use for 'CapCut kholo', 'DaVinci kholo', 'Premiere kholo'."""
    key = str(name or "").lower()
    key = "davinci" if "vinci" in key else "premiere" if "premiere" in key else "capcut" if "cap" in key else key
    if key not in _EDITORS:
        return "Could not open: editor must be capcut, davinci or premiere."
    label = _EDITORS[key][0]
    path = _find_editor(key)
    if not path:
        raise DirectReply(f"Sir, {label} is PC pe install nahi hai.", ok=False)
    if DRY_RUN:
        return _dry_run(f"open {label}")
    os.startfile(path)
    return f"Opened {label}"


# ============================================
# 10. PC LOCK
# ============================================
@tool("Locking PC...", needs=LOCK_WORDS)
def lock_pc() -> str:
    """Lock the Windows PC (goes to the lock screen)."""
    if DRY_RUN:
        return _dry_run("lock PC (LockWorkStation)")
    import ctypes
    ctypes.windll.user32.LockWorkStation()         # Windows ka apna lock function
    return "PC locked"


# ============================================
# 11. SHUTDOWN / RESTART - khatarnak! Pehle confirm karta hai
# ============================================
@tool("Asking confirmation for shutdown...", needs=SHUTDOWN_WORDS)
def shutdown_pc() -> str:
    """Shut down (power off) the computer. The user is asked to confirm first."""
    # Neeche har jawab DirectReply hai: seedha bolo, AI ke paas wapas mat bhejo (fast)
    if not confirm("Sir, pakka? PC shutdown kar doon?"):
        raise DirectReply("Theek hai sir, shutdown cancel kar diya.")
    if DRY_RUN:
        _dry_run("shutdown /s /t 10")
        raise DirectReply("Test mode hai sir, isliye PC sach mein band nahi hua.")
    subprocess.run(["shutdown", "/s", "/t", "10"])   # 10 second baad band
    raise DirectReply("PC 10 second mein band ho jaayega, sir.")


@tool("Asking confirmation for restart...", needs=RESTART_WORDS)
def restart_pc() -> str:
    """Restart the computer. The user is asked to confirm first."""
    if not confirm("Sir, pakka? PC restart kar doon?"):
        raise DirectReply("Theek hai sir, restart cancel kar diya.")
    if DRY_RUN:
        _dry_run("shutdown /r /t 10")
        raise DirectReply("Test mode hai sir, isliye PC sach mein restart nahi hua.")
    subprocess.run(["shutdown", "/r", "/t", "10"])   # 10 second baad restart
    raise DirectReply("PC 10 second mein restart ho jaayega, sir.")


# ============================================
# 12. WEATHER - Open-Meteo (free, bina API key ke, pakka data)
# ============================================
# Open-Meteo mausam ko number (code) mein batata hai - unka matlab
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "heavy showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


last_weather = None    # Aakhri weather ka data (dictionary)
_city_cache = {}       # Shahar -> location (latitude/longitude), baar-baar na dhoondhna pade


@tool("Checking weather: {city}...")
def get_weather(city: str) -> str:
    """Get the current weather and today's forecast for a city (temperature, feels-like,
    humidity, rain chance, wind). Use this for ANY weather/mausam/temperature/rain
    question instead of web_search."""
    import httpx     # Internet se data laane ke liye (google-genai ke saath aa chuka hai)

    # Step 1: Shahar ka naam -> latitude/longitude (Open-Meteo geocoding)
    # Ek baar mil gaya to yaad rakho - shahar ki jagah badalti nahi (agli baar fast)
    key = city.lower().strip()
    if key not in _city_cache:
        geo = httpx.get("https://geocoding-api.open-meteo.com/v1/search",
                        params={"name": city, "count": 1}, timeout=10).json()
        if not geo.get("results"):
            return f"Could not find a city named '{city}'."
        _city_cache[key] = geo["results"][0]
    place = _city_cache[key]

    # Step 2: Us jagah ka mausam
    data = httpx.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": place["latitude"], "longitude": place["longitude"],
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                   "weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 1,
    }, timeout=10).json()
    now, day = data["current"], data["daily"]

    # shortcuts.py isse Hinglish jawab banata hai
    global last_weather
    last_weather = {
        "city": place["name"], "desc": WEATHER_CODES.get(now["weather_code"], "unknown"),
        "temp": round(now["temperature_2m"]), "feels": round(now["apparent_temperature"]),
        "min": round(day["temperature_2m_min"][0]), "max": round(day["temperature_2m_max"][0]),
        "rain": day["precipitation_probability_max"][0],
    }
    # UI ka Weather panel update karo
    ui.set_weather(last_weather["city"], last_weather["temp"], last_weather["desc"])

    return (f"{place['name']}, {place.get('country', '')}: "
            f"{WEATHER_CODES.get(now['weather_code'], 'unknown')}, "
            f"{now['temperature_2m']:.0f}°C (feels like {now['apparent_temperature']:.0f}°C), "
            f"humidity {now['relative_humidity_2m']}%, wind {now['wind_speed_10m']:.0f} km/h. "
            f"Today: min {day['temperature_2m_min'][0]:.0f}°C, max {day['temperature_2m_max'][0]:.0f}°C, "
            f"rain chance {day['precipitation_probability_max'][0]}%.")


# ============================================
# 13. LONG-TERM MEMORY - Krish ki baatein yaad rakhna / bhoolna (memory.py)
# ============================================
@tool("Saving to memory: {fact}...")
def save_memory(fact: str) -> str:
    """Save an important long-term fact about Krish, e.g. birthday, likes/dislikes,
    friends' or family names, goals. Use when Krish says 'yaad rakhna' / 'remember'
    or shares personal info. Write the fact as a short clear sentence, e.g.
    'Krish ka birthday 9 June ko hai'. If Krish CORRECTS an earlier fact, save the full
    corrected fact (it replaces the old one automatically). Write spelled usernames/IDs
    as one word, e.g. 'krrish972'."""
    import memory
    status, old = memory.add(fact)
    if status == "updated":
        return f"Updated memory: {old} -> {fact}"
    if status == "same":
        return f"Already in memory: {fact}"
    return f"Saved to memory: {fact}"


@tool("Removing from memory: {what}...", needs=FORGET_WORDS)
def delete_memory(what: str) -> str:
    """Delete a saved memory when Krish says 'bhool jao' / 'forget'. 'what' = the key
    words of the fact to forget (e.g. 'birthday'), or 'all' to forget everything
    (asks Krish to confirm first)."""
    import memory
    if what.strip().lower() in ("all", "everything", "sab", "sab kuch", "saara", "सब"):
        if not confirm("Sir, pakka? Saari memory mita doon?"):
            raise DirectReply("Theek hai sir, memory waise hi rahegi.")
        return f"Deleted all {memory.clear()} memories."
    removed = memory.remove(what)
    if not removed:
        return f"Nothing in memory matched '{what}'."
    return "Deleted from memory: " + "; ".join(removed)


# ============================================
# 14. SCREEN VISION - screen dekh ke sawaal ka jawab (vision.py)
# ============================================
@tool("Scanning screen...", needs=SCREEN_WORDS)
def look_at_screen(question: str) -> str:
    """Look at Krish's screen (takes a screenshot) and answer a question about it, e.g.
    'screen pe kya hai', 'is error ko samjhao', 'is code mein galti batao'. Pass
    Krish's question as-is. Only use when Krish asks about Krish's own screen."""
    import vision
    jpeg = vision.capture_screen()      # Sirf memory mein - koi file nahi banti
    try:
        answer, used = vision.ask_about_image(jpeg, question)
    finally:
        del jpeg                         # Screenshot turant mita do (kahin save nahi)
    ui.log(f"Vision: {used}")
    if not answer:
        return "Error: vision model returned an empty answer."
    # Vision ka jawab seedha bolo - main AI ke paas dobara bhejne ka time bachao
    raise DirectReply(answer)


# ============================================
# 15. WHATSAPP + CALLS (whatsapp.py, notifications.py) - koi number file nahi
#   - Contact WhatsApp Desktop ke search se dhoondhte hain (jaise insaan)
#   - Chat khulne pe header ka naam padh ke confirm, tabhi bhejna/call
#   - DRY_RUN: search + chat kholna chalta hai, Enter / call button NAHI
#   - Message ka text terminal log mein nahi jaata; naam mein number ho to masked
# ============================================
_YES = {"haan", "han", "ha", "haa", "yes", "yeah", "yep", "ok", "okay", "bhejo", "bhej", "send",
        "pakka", "theek", "sure", "sahi", "हां", "हाँ"}
_NO = {"nahi", "nahin", "no", "mat", "cancel", "ruko", "rehne", "नहीं"}
_EDIT = {"polite", "english", "hindi", "hinglish", "formal", "casual", "chhota", "short", "lamba",
         "badal", "badlo", "change", "sudhar", "sudhaaro", "likh", "likho", "bana", "banao",
         "rewrite", "friendly", "sweet", "achha", "acchha", "aur", "add", "jodo", "hatao"}
# "Khud ko message bhejo" / "mujhe bhejo" -> WhatsApp ki apni "(You)" chat
_SELF = {"khud", "khud ko", "mujhe", "mujhko", "me", "myself", "self", "apne aap", "apne aap ko",
         "you", "main", "mere ko", "apni chat", "khud ki chat"}


def _answer_kind(answer):
    """Confirm ke jawab ko samjho: 'yes' / 'no' / 'edit' (message badalna hai)."""
    words = set(re.findall(r"[^\s.,!?।]+", (answer or "").lower()))
    if not words:
        return "no"
    if words & _NO and not words & _EDIT:
        return "no"
    if words & _EDIT or (len(words) > 2 and not words <= _YES):
        return "edit"
    if words & _YES:
        return "yes"
    return "no"


def _shown(title):
    """Bolne/dikhane ke liye chat ka naam: apni chat = "aapki apni (You)",
    unsaved number = "number ...1154" (pura number kabhi nahi, "star star" bhi nahi)."""
    import whatsapp
    if "(You)" in title:
        return "aapki apni (You)"
    return whatsapp.mask(title).replace("***", "number ...")


def _open_chat(name):
    """WhatsApp mein naam search karo aur sahi chat kholo. Return: (window, message_box, title).
    Na mile / cancel ho to DirectReply (kuch bheja nahi jaata)."""
    import whatsapp
    wanted = name.strip().lower()
    self_chat = wanted in _SELF
    if self_chat:
        # Apni chat search se NAHI ("You" se "Yash" bhi aata) - chat list mein sabse upar se
        sid = whatsapp.step("Opening chat", "(You)", "running")
        win = whatsapp._window()
        title, box, _ = whatsapp.open_self(win)
        if not title:
            whatsapp.step("Opening chat", "(You)", "failed", sid)
            whatsapp.clear_search(win)
            raise DirectReply("Sir, chat nahi khul payi. Kuch nahi bheja.", ok=False)
        title = title if "(You)" in title else title + " (You)"
        whatsapp.step("Chat opened", title, "done", sid)
        return win, box, title

    sid = whatsapp.step("Searching WhatsApp", name, "running")
    win, results = whatsapp.search(name)
    found = whatsapp._best(results, name)
    if not found:
        whatsapp.step("Searching WhatsApp", "Koi result nahi", "failed", sid)
        whatsapp.clear_search(win)
        if whatsapp.search_error:
            raise DirectReply(f"Sir, WhatsApp search nahi chal paya ({whatsapp.search_error}). Kuch nahi bheja.", ok=False)
        raise DirectReply(f"Sir, WhatsApp mein '{name}' naam nahi mila. Kuch nahi bheja.", ok=False)
    whatsapp.step("Searching WhatsApp", f"{len(found)} result", "done", sid)

    choice = found[0]
    if len(found) > 1:
        titles = [_shown(t) for t, _ in found[:5]]
        answer = ask_user(f"Sir, {len(found)} {name} mile: {', '.join(titles)}. Kaunsa?")
        choice = whatsapp.pick(found[:5], answer)
        if choice is None:
            whatsapp.clear_search(win)
            raise DirectReply("Theek hai sir, koi chat nahi kholi. Kuch nahi bheja.", ok=False)

    # Max 2 koshish (keyboard Down+Enter, phir click) - dobara search/type nahi
    title, box, _ = whatsapp.open_result(win, choice[1], choice[0])
    if not title:
        whatsapp.step("Opening chat", choice[0][:40], "failed")
        whatsapp.clear_search(win)
        raise DirectReply("Sir, chat nahi khul payi. Kuch nahi bheja.", ok=False)
    whatsapp.step("Chat opened", title, "done")
    return win, box, title


def _confirm_message(title, message):
    """"Rahul Sharma ki chat khuli hai. Bhejun: '...'?" - haan pe message, nahi pe None.
    "Polite bana do" / "English mein likh do" -> AI se sudhaar ke DOBARA poochho (max 3 baar)."""
    import brain
    for _ in range(4):
        answer = ask_user(f"{_shown(title)} ki chat khuli hai. Bhejun: '{message}'? Haan ya nahi")
        kind = _answer_kind(answer)
        if kind == "yes":
            return message
        if kind == "no":
            return None
        ui.log("Message sudhaar raha hoon...")
        message = brain.rewrite_message(message, answer)
    return None


@tool("Sending WhatsApp: {contact}...", needs=MSG_WORDS)
def send_whatsapp(contact: str, message: str) -> str:
    """Send a WhatsApp message. contact = the chat name as Krish said it (e.g. 'Rahul', 'Mom'),
    or 'khud' for Krish's own (You) chat. JARVIS searches WhatsApp Desktop, opens the chat,
    reads its name and asks Krish to confirm before sending. Pass the message as Krish said it."""
    import whatsapp
    win, box, title = _open_chat(contact)
    final = _confirm_message(title, message.strip())
    if not final:
        raise DirectReply("Theek hai sir, message nahi bheja.", ok=False)
    if DRY_RUN:
        _dry_run(f"paste message ({len(final)} characters) + Enter in chat '{whatsapp.mask(title)}'")
        whatsapp.step("Send (DRY RUN)", title, "done")
        raise DirectReply(f"Test mode hai sir. {_shown(title)} ki chat khuli, par message nahi bheja.")
    sid = whatsapp.step("Sending", title, "running")
    if whatsapp.send_in_open_chat(win, box, final):
        whatsapp.step("Sent", title, "done", sid)
        import notifications
        notifications.mark_read(title)
        raise DirectReply(f"Bhej diya, sir. Message {_shown(title)} ki chat mein dikh raha hai.")
    whatsapp.step("Sent?", "Chat mein nahi dikha", "failed", sid)
    raise DirectReply("Sir, Enter daba diya par message chat mein dikha nahi. WhatsApp khud check kar lijiye.", ok=False)


@tool("WhatsApp call: {contact}...", needs=CALL_WORDS)
def whatsapp_call(contact: str, video: bool = False) -> str:
    """Start a WhatsApp voice call (video=False) or video call (video=True). contact = chat name
    as Krish said it. JARVIS opens the chat, reads its name and asks Krish to confirm first."""
    import whatsapp
    kind = "video call" if video else "voice call"
    win, box, title = _open_chat(contact)
    if not confirm(f"{_shown(title)} ki chat khuli hai. {kind.capitalize()} karun?"):
        raise DirectReply(f"Theek hai sir, {kind} nahi kiya.", ok=False)
    if DRY_RUN:
        _dry_run(f"press WhatsApp '{kind}' button in chat '{whatsapp.mask(title)}'")
        whatsapp.step(f"{kind.capitalize()} (DRY RUN)", title, "done")
        raise DirectReply(f"Test mode hai sir. {_shown(title)} ki chat khuli, par {kind} nahi lagaya.")
    sid = whatsapp.step(f"Starting {kind}", title, "running")
    whatsapp.press_call(win, video=bool(video))
    whatsapp.step(f"{kind.capitalize()} started", title, "done", sid)
    raise DirectReply(f"{_shown(title)} ko {kind} laga raha hoon, sir.")


@tool("Ending call...", needs=END_CALL_WORDS)
def end_call() -> str:
    """End (hang up) the current WhatsApp call."""
    if DRY_RUN:
        _dry_run("click WhatsApp 'End call' button")
        raise DirectReply("Test mode hai sir, call sach mein nahi kaati.")
    import whatsapp
    if whatsapp.end_call():
        raise DirectReply("Call kaat di, sir.")
    raise DirectReply("Sir, koi chalti WhatsApp call nahi mili.", ok=False)


@tool("Reading WhatsApp messages...", needs=READ_WORDS)
def read_messages() -> str:
    """Read out the last 5 unread WhatsApp messages (from Windows notifications)."""
    global private_reply
    import notifications
    if notifications.status() == "no access":
        raise DirectReply("Sir, Windows ne notifications padhne ki permission nahi di. Settings > Privacy & "
                          "security > Notifications mein 'Let apps access your notifications' ON kijiye.", ok=False)
    items = notifications.unread(5)
    if not items:
        raise DirectReply("Sir, koi naya WhatsApp message nahi hai.")
    private_reply = True       # Message ka text terminal mein nahi dikhega
    parts = [f"{i['sender']}: '{i['text']}'" for i in items]
    head = "Sir, 1 message hai. " if len(items) == 1 else f"Sir, {len(items)} messages hain. "
    raise DirectReply(head + ". ".join(parts) + ".")


# ============================================
# Saare tools ki list - brain.py ye list Gemini ko deta hai
# ============================================
ALL_TOOLS = [
    web_search, get_weather, open_website, play_on_youtube, open_app, close_app,
    get_time_date, system_info, take_screenshot, set_volume, set_mute, volume_change,
    media_control, brightness, find_files, open_file,
    note_add, notes_list, note_delete,
    reminder_add, task_list, task_delete, tasks_clear, reminder_snooze,
    content_help, copy_last_content, open_editor,
    lock_pc, shutdown_pc, restart_pc,
    save_memory, delete_memory, look_at_screen,
    send_whatsapp, whatsapp_call, end_call, read_messages,
]
