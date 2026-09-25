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
    def __init__(self, reply):
        super().__init__(reply)
        self.reply = reply


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

# Volume/mute: "chup raho" (JARVIS chup ho) pe PC mute na ho jaaye
VOLUME_WORDS = {"volume", "mute", "unmute", "awaaz", "awaz", "aawaz", "sound", "speaker",
                "आवाज़", "आवाज", "वॉल्यूम", "म्यूट"}
PLAY_WORDS = {"play", "chalao", "chala", "bajao", "baja", "sunao", "lagao", "laga",
              "चलाओ", "बजाओ", "सुनाओ", "लगाओ"}


def _asked_for(words):
    """True agar current_request mein in words mein se koi ho."""
    text = current_request.lower()
    tokens = set(re.findall(r"[^\s.,!?।]+", text))
    return any((w in text) if " " in w else (w in tokens) for w in words)


# ============================================
# @tool decorator - har tool pe lagta hai
#   1. SAFETY LOCK check (needs=... diya ho to)
#   2. UI pe 'thinking' state aur message dikhata hai
#   3. try/except - tool fail ho to crash nahi, error message AI ko jaata hai
#   4. call_log mein likhta hai ki tool chala
# ============================================
def tool(message, needs=None):
    def decorator(func):
        @functools.wraps(func)     # Gemini ko asli function ka naam/docstring dikhe
        def wrapper(*args, **kwargs):
            ui.set_state("thinking")

            # --- Safety lock: kya Krish ne abhi ye kaam maanga hai? ---
            if needs and not _asked_for(needs):
                ui.log(f"BLOCKED {func.__name__}: current message did not ask for it")
                result = (f"BLOCKED for safety: Krish's current message did not ask for "
                          f"{func.__name__}. Do NOT call it again. Just answer Krish's "
                          f"current message normally.")
                call_log.append((func.__name__, result))
                return result

            try:
                # message mein {name} jaisi jagah ho to asli value bhar do
                values = inspect.signature(func).bind(*args, **kwargs).arguments
                ui.log(message.format(**values))
            except (KeyError, IndexError, TypeError):
                ui.log(message.split(":")[0].split("{")[0].strip() + "...")
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                ui.log(f"Error: {e}")
                result = f"Error while running {func.__name__}: {e}"
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
# Saare tools ki list - brain.py ye list Gemini ko deta hai
# ============================================
ALL_TOOLS = [
    web_search, get_weather, open_website, play_on_youtube, open_app, close_app,
    get_time_date, system_info, take_screenshot, set_volume, set_mute,
    lock_pc, shutdown_pc, restart_pc,
    save_memory, delete_memory, look_at_screen,
]
