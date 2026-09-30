# ============================================
# phone.py - Android phone control (ADB, sirf ghar ka WiFi)
#   - Sirf Google ka official adb (tools/platform-tools/adb.exe).
#   - Free "adb shell" command KABHI nahi: neeche ke fixed templates hi chalte hain, args validate hote hain.
#   - Phone ka address .env PHONE_ADB_ADDRESS (ip:port) - sirf private/LAN IP maana jaata hai, kabhi print/log nahi.
#   - Payment/UPI/bank, dialer/SMS, Settings, Play Store, file-manager apps kabhi nahi khulte, aur unke upar
#     (foreground mein hon to) tap/type/media bhi nahi chalta.
#   - Screenshot sirf RAM mein (disk pe nahi). Log mein kabhi text/app naam nahi.
#   Tests `_adb` ko fake karte hain (ek hi jagah jahan se adb chalta hai).
# ============================================
import ipaddress
import os
import re
import subprocess

from dotenv import load_dotenv

load_dotenv()

BASE = os.path.dirname(os.path.abspath(__file__))
ADB_EXE = os.path.join(BASE, "tools", "platform-tools", "adb.exe")
TIMEOUT = 8

NOT_CONNECTED = "phone connected nahi hai, Wireless debugging on karo"


class PhoneError(Exception):
    """Phone ka kaam nahi hua. Message Krish ko bolne layak hai (koi private data nahi)."""


# ---------- adb chalane ki EK jagah ----------
def address():
    """.env se phone ka ip:port. Sirf private (ghar ke WiFi wala) IPv4 chalta hai, warna None."""
    raw = os.getenv("PHONE_ADB_ADDRESS", "").strip()
    m = re.fullmatch(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})", raw)
    if not m:
        return None
    try:
        ip = ipaddress.ip_address(m[1])
    except ValueError:
        return None
    if not ip.is_private or ip.is_loopback or not (1 <= int(m[2]) <= 65535):
        return None      # internet wala address kabhi nahi
    return raw


def _adb(args, binary=False, timeout=TIMEOUT):
    """adb.exe ko FIXED args list se chalao (shell=False). Output text (ya binary=True mein bytes).
    Adb na mile / phone na jude to PhoneError."""
    if not os.path.isfile(ADB_EXE):
        raise PhoneError("adb nahi mila (tools/platform-tools)")
    try:
        p = subprocess.run([ADB_EXE, *args], capture_output=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise PhoneError(NOT_CONNECTED)
    if p.returncode != 0:
        raise PhoneError(NOT_CONNECTED)
    return p.stdout if binary else p.stdout.decode("utf-8", "replace")


def _target():
    addr = address()
    if not addr:
        raise PhoneError("PHONE_ADB_ADDRESS .env mein nahi hai (ya ghar ke WiFi ka address nahi)")
    return addr


def _shell(*parts, binary=False):
    """`adb -s <phone> shell <parts>` - parts sirf is file ke fixed templates se aate hain."""
    return _adb(["-s", _target(), "exec-out" if binary else "shell", *parts], binary=binary)


def connect():
    """Phone se jud jao (pehle se jura ho to kuch nahi hota). PhoneError agar na jude."""
    addr = _target()
    try:
        out = _adb(["connect", addr])
    except PhoneError:
        raise PhoneError(NOT_CONNECTED)
    if "connected" not in out.lower() or "cannot" in out.lower() or "failed" in out.lower():
        raise PhoneError(NOT_CONNECTED)
    return True


def ensure():
    """Jura hua device chahiye: pehle check, na ho to ek baar connect."""
    try:
        _shell("echo", "ok")
    except PhoneError:
        connect()
        _shell("echo", "ok")


# ---------- apps ki safe list ----------
BLOCKED_WORDS = ("upi", "paisa", "phonepe", "paytm", "bhim", "gpay", "wallet", "payment", "bank",
                 "cred", "mobikwik", "freecharge", "razorpay", "npci", "sbi", "hdfc", "icici", "axis",
                 "kotak", "finance", "invest", "trade", "zerodha", "groww")
BLOCKED_PACKAGES = {
    "com.android.settings", "com.samsung.android.settings", "com.android.vending",         # settings / Play Store
    "com.android.packageinstaller", "com.google.android.packageinstaller",
    "com.android.dialer", "com.google.android.dialer", "com.samsung.android.dialer",       # call
    "com.android.server.telecom", "com.samsung.android.incallui",
    "com.android.mms", "com.google.android.apps.messaging", "com.samsung.android.messaging",  # SMS
    "com.sec.android.app.myfiles", "com.google.android.apps.nbu.files",                     # files delete
    "com.android.documentsui", "com.google.android.documentsui",
}
ALIASES = {
    "whatsapp": "com.whatsapp", "youtube": "com.google.android.youtube",
    "chrome": "com.android.chrome", "instagram": "com.instagram.android",
    "spotify": "com.spotify.music", "maps": "com.google.android.apps.maps",
    "gmail": "com.google.android.gm", "telegram": "org.telegram.messenger",
    "camera": "com.sec.android.app.camera", "gallery": "com.sec.android.gallery3d",
    "facebook": "com.facebook.katana", "snapchat": "com.snapchat.android",
    "netflix": "com.netflix.mediaclient", "photos": "com.google.android.apps.photos",
    "clock": "com.sec.android.app.clockpackage", "calculator": "com.sec.android.app.popupcalculator",
}
_PKG = re.compile(r"[a-zA-Z][\w]*(?:\.[\w]+)+")


def is_blocked(package):
    p = package.lower()
    return p in BLOCKED_PACKAGES or any(w in p for w in BLOCKED_WORDS)


def installed_packages():
    """Phone ke installed package naam (system + user)."""
    out = _shell("pm", "list", "packages")
    return sorted({l[8:].strip() for l in out.splitlines() if l.startswith("package:")})


def resolve_app(name):
    """Bole hue naam se ek package. (package, None) ya (None, Krish ko bolne wali wajah).
    Blocked app ka naam wajah mein bhi nahi kholta."""
    key = re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()
    if not key:
        return None, "Kaunsa app kholna hai, sir?"
    if any(w in key.replace(" ", "") for w in BLOCKED_WORDS):
        return None, "Ye app main phone pe nahi kholunga, sir (payment/bank jaisa hai)."
    ensure()
    pkgs = installed_packages()
    cands = []
    if key in ALIASES and ALIASES[key] in pkgs:
        cands = [ALIASES[key]]
    else:
        toks = key.split()
        cands = [p for p in pkgs if all(t in p.lower() for t in toks)]
        # user apps ko system apps se upar rakho (chhota naam pehle)
        cands.sort(key=len)
        if len(cands) > 1 and any(c.split(".")[-1] == key.replace(" ", "") for c in cands):
            cands = [c for c in cands if c.split(".")[-1] == key.replace(" ", "")][:1]
    if not cands:
        return None, "Ye app phone mein nahi mila, sir."
    if len(cands) > 1:
        return None, "Kai apps match hue, sir. Poora naam bolo."
    pkg = cands[0]
    if is_blocked(pkg) or not _PKG.fullmatch(pkg):
        return None, "Ye app main phone pe nahi kholunga, sir."
    return pkg, None


def foreground_package():
    """Abhi screen pe kaunsa app hai (package). Na mile to ''."""
    try:
        out = _shell("dumpsys", "window")
    except PhoneError:
        raise
    m = re.search(r"mCurrentFocus=.*?\{[^}]*?\s([\w.]+)/", out) or re.search(r"mFocusedApp=.*?\s([\w.]+)/", out)
    return m[1] if m else ""


def guard_foreground():
    """Payment/bank/dialer/settings jaise app screen pe ho to tap/type/media band (PhoneError)."""
    pkg = foreground_package()
    if pkg and is_blocked(pkg):
        raise PhoneError("Is waqt phone pe sensitive app khula hai (payment/settings/calls), sir. "
                         "Isme main kuch nahi karunga.")


# ---------- kaam (sab fixed templates) ----------
def status():
    """(battery %, charging bool)."""
    ensure()
    out = _shell("dumpsys", "battery")
    lvl = re.search(r"level:\s*(\d+)", out)
    if not lvl:
        raise PhoneError("Battery ka status nahi mila")
    powered = re.search(r"(AC|USB|Wireless) powered:\s*true", out) is not None
    return int(lvl[1]), powered


def screenshot():
    """Phone ki screen ki PNG bytes (sirf RAM mein)."""
    ensure()
    png = _shell("screencap", "-p", binary=True)
    if not png.startswith(b"\x89PNG"):
        raise PhoneError("Screenshot nahi mila")
    return png


def screen_size():
    out = _shell("wm", "size")
    m = re.search(r"(\d+)x(\d+)", out)
    if not m:
        raise PhoneError("Screen ka size nahi mila")
    return int(m[1]), int(m[2])


def open_package(pkg):
    if is_blocked(pkg) or not _PKG.fullmatch(pkg):
        raise PhoneError("Ye app main phone pe nahi kholunga, sir.")
    ensure()
    _shell("monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")


TEXT_OK = re.compile(r"[A-Za-z0-9 .,!?@_\-:]{1,200}")


def valid_text(text):
    return bool(TEXT_OK.fullmatch(text or ""))


def type_text(text):
    if not valid_text(text):
        raise PhoneError("Sirf English letters, numbers aur simple punctuation type kar sakta hoon (200 tak), sir.")
    ensure()
    guard_foreground()
    _shell("input", "text", text.replace(" ", "%s"))


def tap(x, y):
    ensure()
    guard_foreground()
    w, h = screen_size()
    if not (0 <= int(x) < w and 0 <= int(y) < h):
        raise PhoneError(f"Tap screen ke andar hona chahiye (0-{w - 1}, 0-{h - 1}), sir.")
    _shell("input", "tap", str(int(x)), str(int(y)))


KEYS = {"back": 4, "home": 3,
        "play": 126, "pause": 127, "playpause": 85, "next": 87, "previous": 88,
        "volume_up": 24, "volume_down": 25}


def key(name):
    if name not in KEYS:
        raise PhoneError("Ye key allowed nahi hai")
    ensure()
    if name not in ("home",):
        guard_foreground()
    _shell("input", "keyevent", str(KEYS[name]))


def media(action):
    a = re.sub(r"[^a-z]+", "_", (action or "").lower()).strip("_")
    a = {"resume": "play", "stop": "pause", "skip": "next", "prev": "previous",
         "louder": "volume_up", "quieter": "volume_down", "volume_badhao": "volume_up",
         "volume_kam": "volume_down", "up": "volume_up", "down": "volume_down"}.get(a, a)
    if a not in ("play", "pause", "playpause", "next", "previous", "volume_up", "volume_down"):
        raise PhoneError("Media action: play, pause, next, previous, volume_up ya volume_down.")
    key(a)
    return a
