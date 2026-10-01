# ============================================
# phone.py - Android phone control (ADB, sirf ghar ka WiFi)
#   - Sirf Google ka official adb (tools/platform-tools/adb.exe).
#   - Free "adb shell" command KABHI nahi: neeche ke fixed templates hi chalte hain, args validate hote hain.
#   - Phone ka address .env PHONE_ADB_ADDRESS (ip:port) - sirf private/LAN IP maana jaata hai, kabhi print/log nahi.
#   - Payment/UPI/bank, dialer/SMS, Settings, Play Store, file-manager apps kabhi nahi khulte, aur unke upar
#     (foreground mein hon to) tap/type/media bhi nahi chalta.
#   - Screenshot sirf RAM mein (disk pe nahi). Log mein kabhi text/app naam nahi.
#   - Screen ka text `uiautomator dump` se padhte hain (password wale nodes chhupaye), phir button/box ke
#     NAAM se tap hota hai - coordinates bolne ki zaroorat nahi. Dump XML RAM mein hai (phone par /sdcard
#     par temp file turant delete ho jaati hai).
#   Tests `_adb` ko fake karte hain (ek hi jagah jahan se adb chalta hai).
# ============================================
import ipaddress
import os
import re
import subprocess
import xml.etree.ElementTree as ET

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


def _shell(*parts, binary=False, timeout=TIMEOUT):
    """`adb -s <phone> shell <parts>` - parts sirf is file ke fixed templates se aate hain."""
    return _adb(["-s", _target(), "exec-out" if binary else "shell", *parts], binary=binary, timeout=timeout)


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


def foreground_package(dump=None):
    """Abhi screen pe kaunsa app hai (package). Na mile to ''."""
    out = dump if dump is not None else _shell("dumpsys", "window")
    m = re.search(r"mCurrentFocus=.*?\{[^}]*?\s([\w.]+)/", out) or re.search(r"mFocusedApp=.*?\s([\w.]+)/", out)
    return m[1] if m else ""


def screen_state(dump=None):
    """(screen_on, locked): uiautomator sirf tab asli screen dikhata hai jab screen on aur unlock ho."""
    out = dump if dump is not None else _shell("dumpsys", "window")
    return not re.search(r"\bmAwake=false\b", out), bool(re.search(r"mDreamingLockscreen=true", out))


def guard_screen(dump=None):
    """Screen off ya lock hai to PhoneError (tab tap/type ka koi matlab nahi - chup-chaap fail na ho)."""
    on, locked = screen_state(dump)
    if not on:
        raise PhoneError("Phone ka screen off hai, sir (on karke phir boliye).")
    if locked:
        raise PhoneError("Phone ka screen lock hai, sir (unlock karke phir boliye).")


def guard_foreground(dump=None):
    """Payment/bank/dialer/settings jaise app screen pe ho to tap/type/media band (PhoneError)."""
    pkg = foreground_package(dump)
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
    dump = _shell("dumpsys", "window")     # ek hi dump: screen state + foreground app
    guard_screen(dump)
    guard_foreground(dump)
    _shell("input", "text", text.replace(" ", "%s"))


def tap(x, y):
    ensure()
    dump = _shell("dumpsys", "window")     # ek hi dump: screen state + foreground app
    guard_screen(dump)
    guard_foreground(dump)
    w, h = screen_size()
    if not (0 <= int(x) < w and 0 <= int(y) < h):
        raise PhoneError(f"Tap screen ke andar hona chahiye (0-{w - 1}, 0-{h - 1}), sir.")
    _shell("input", "tap", str(int(x)), str(int(y)))


KEYS = {"back": 4, "home": 3, "enter": 66, "search": 84, "delete": 67, "tab": 61,
        "play": 126, "pause": 127, "playpause": 85, "next": 87, "previous": 88,
        "volume_up": 24, "volume_down": 25}


def key(name):
    if name not in KEYS:
        raise PhoneError("Ye key allowed nahi hai")
    ensure()
    if name not in ("home",):
        dump = _shell("dumpsys", "window")
        guard_screen(dump)
        guard_foreground(dump)
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


# ============================================
# SCREEN PADHNA AUR NAAM SE TAP (uiautomator)
#   Screen ka XML -> nodes (text/content-desc/resource-id + jagah) -> "Search" jaise naam se tap.
#   Password wale nodes, lambe (>40 chars) labels aur chhote (1x1) nodes chhupaye jaate hain - AI ko
#   sirf button/box ke naam dikhte hain, screen ka poora text nahi.
# ============================================
UI_XML = "/sdcard/jarvis_ui.xml"          # temp file (dump ke baad turant delete)
MAX_LABEL = 40                            # isse lamba "label" asli button nahi hota
_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

last_list = []        # Aakhri screen listing: [(label, x, y)] - sirf RAM (number se tap ke liye)


class Node:
    """uiautomator XML ka ek UI node: naam (text/content-desc/id) + screen par jagah."""

    __slots__ = ("text", "desc", "rid", "cls", "bounds", "clickable", "scrollable", "secret")

    def __init__(self, attrs):
        self.text = (attrs.get("text") or "").strip()
        self.desc = (attrs.get("content-desc") or "").strip()
        self.rid = (attrs.get("resource-id") or "").strip()
        self.cls = (attrs.get("class") or "").strip()
        self.clickable = attrs.get("clickable") == "true"
        self.scrollable = attrs.get("scrollable") == "true"
        self.secret = attrs.get("password") == "true"
        m = _BOUNDS.fullmatch((attrs.get("bounds") or "").strip())
        self.bounds = tuple(int(v) for v in m.groups()) if m else (0, 0, 0, 0)

    @property
    def label(self):
        """Dikhne layak naam: text, warna content-desc, warna resource-id ka aakhri hissa."""
        raw = self.text or self.desc or (self.rid.rsplit("/", 1)[-1] if self.rid else "")
        return " ".join(raw.split())[:MAX_LABEL]

    @property
    def from_id(self):
        """Sirf resource-id se bana naam (text/content-desc khaali) - aksar layout container jaisa bekaar naam."""
        return not (self.text or self.desc)

    @property
    def tappable(self):
        """Control hai jo user chhoo sakta hai (ya text daalne wala box)."""
        return self.clickable or self.kind in ("EditText", "CheckBox", "RadioButton", "ToggleButton",
                                               "SeekBar", "Switch")

    @property
    def kind(self):
        """Control ka type (Button/Edit/TextView...) - View/ViewGroup generic hain, chhupaye."""
        k = self.cls.rsplit(".", 1)[-1]
        return "" if k in ("", "View", "ViewGroup", "ViewStub", "FrameLayout", "LinearLayout",
                           "RelativeLayout", "ConstraintLayout", "android.view.View") else k

    @property
    def center(self):
        l, t, r, b = self.bounds
        return (l + r) // 2, (t + b) // 2

    @property
    def size(self):
        l, t, r, b = self.bounds
        return max(0, r - l) * max(0, b - t)

    def line(self, i):
        return f"{i}. {self.label}" + (f" ({self.kind})" if self.kind else "") + \
               (", tapne layak" if self.clickable else "")


def _clean_xml(raw):
    """uiautomator ke output se sirf XML part (status line hatao)."""
    i = raw.find("<?xml")
    if i < 0:
        i = raw.find("<hierarchy")
    if i < 0:
        return ""
    k = raw.rfind("</hierarchy>")
    return raw[i:k + 12] if k > 0 else raw[i:raw.rfind(">") + 1]


DUMP_TIMEOUT = 25      # uiautomator dump asli phone par 8-10 s le sakta hai


def dump_xml():
    """Phone ki screen ka UI XML (string). Pehle /dev/tty, warna /sdcard temp file (padhke delete).
    Screen lock/off ya dump na mile to PhoneError."""
    ensure()
    xml = _clean_xml(_shell("uiautomator", "dump", "/dev/tty", timeout=DUMP_TIMEOUT))
    if not xml:
        try:
            _shell("uiautomator", "dump", UI_XML, timeout=DUMP_TIMEOUT)
            xml = _clean_xml(_shell("cat", UI_XML, timeout=DUMP_TIMEOUT))
        finally:
            try:
                _shell("rm", "-f", UI_XML)        # temp file kabhi bachta nahi
            except PhoneError:
                pass
    if not xml:
        raise PhoneError("Screen ka text nahi mila (phone ka screen on ya unlock hona chahiye)")
    return xml


def screen_nodes():
    """Screen ke UI nodes, upar se neeche (XML order). Chhupaye jaate hain: password nodes, 1-pixel/zero-size,
    be-laal nodes, aur sirf resource-id wale bekaar container (jaise app_bar/coordinator) - sirf buttons,
    boxes aur text wahi chhupaye nahi jaate."""
    try:
        root = ET.fromstring(dump_xml())
    except ET.ParseError:
        raise PhoneError("Screen ka text theek se nahi padha (dobara try karo)")
    guard_screen()          # dump lock screen ka dikhta hai - asli screen tabhi, jab on + unlock ho
    out = []
    for el in root.iter("node"):
        n = Node(el.attrib)
        l, t, r, b = n.bounds
        if n.secret or r <= l or b <= t or n.size < 100 or not n.label:
            continue
        if n.from_id and not n.tappable:
            continue
        out.append(n)
    if not out:
        raise PhoneError("Screen pe koi button ya text nahi dikha (screen lock ho sakta hai)")
    return out


def _score(node, needle):
    """Bole hue shabd se kitna match: 100+ exact, 50+ andar, 20+ poora shabd. text > content-desc > id."""
    best = 0
    for weight, val in ((4, node.text), (3, node.desc), (1, node.rid.rsplit("/", 1)[-1] if node.rid else "")):
        v = " ".join((val or "").lower().split())
        if not v:
            continue
        if v == needle:
            best = max(best, 100 + weight)
        elif needle in v:
            best = max(best, 50 + weight)
        elif needle in v.split():
            best = max(best, 20 + weight)
    return best


def _norm(text):
    return " ".join((text or "").lower().split())


def list_screen(query="", limit=30):
    """Screen par dikhne wali cheezein (label + type + tapne layak), list bana ke aur `last_list` bharta hai.
    query diya ho to sirf usi shabd wali cheezein. list_screen("search") -> ['1. Search (Edit), tapne layak']"""
    global last_list
    key = _norm(query)
    picked, seen = [], set()
    for n in screen_nodes():
        label = n.label
        if label.lower() in seen:                 # wahi naam 2 baar mat dikhao
            continue
        if key and not (key in label.lower() or any(w in label.lower() for w in key.split() if len(w) > 2)):
            continue
        seen.add(label.lower())
        picked.append(n)
        if len(picked) >= max(1, int(limit)):
            break
    if picked:
        last_list = [(n.label, *n.center) for n in picked]     # RAM
    return [n.line(i) for i, n in enumerate(picked, 1)]


def _match(label, nodes):
    """Sabse achha match: (score, clickable, size, -y, node) - chhota list."""
    key = _norm(label)
    scored = [t for t in ((_score(n, key), n) for n in nodes) if t[0]]
    if not scored:
        return []
    scored.sort(key=lambda t: (t[0], 1 if t[1].clickable else 0, t[1].size, -t[1].center[1]), reverse=True)
    return [n for _, n in scored]


def resolve_tap(label):
    """Tap kis cheez pe karna hai: (naam, x, y). Na mile ya do jagah ho to PhoneError (wajah Krish ko bolne layak).
    Sirf dhoondta hai, tap nahi karta - confirm se pehle naam dikhane ke liye.
    label number (1, 2, ...) ho to aakhri listing ka uss number wala item (RAM ka `last_list`)."""
    key = _norm(label)
    if not key:
        raise PhoneError("Kya tap karna hai, sir?")
    if key.isdigit():
        i = int(key) - 1
        if not last_list or not 1 <= i < len(last_list):
            raise PhoneError("Sir, pehle phone ki screen padh lo, phir number bolo.")
        return last_list[i]
    nodes = screen_nodes()
    if not nodes:
        raise PhoneError("Sir, phone ki screen ka text nahi mila (screen on ya unlock karo).")
    best = _match(key, nodes)
    if not best:
        raise PhoneError(f"Sir, phone ki screen pe '{label}' nahi mila.")
    if len(best) > 1 and _score(best[0], key) == _score(best[1], key):
        raise PhoneError(f"Sir, '{label}' screen pe 2 jagah dikh raha hai ({best[0].label} aur "
                         f"{best[1].label}). Thoda aur batao ya screen padh ke number bolo.")
    x, y = best[0].center
    return best[0].label, x, y


def tap_text(label):
    """Naam de ke tap: pehle naam dhoondo (bina coordinates ke), phir usi ki jagah tap.
    (naam, x, y) wapas - confirm mein naam dikhane ke liye."""
    name, x, y = resolve_tap(label)
    tap(x, y)
    return name, x, y


DIRECTIONS = ("down", "up", "left", "right")
_DIR_WORDS = {"neeche": "down", "upar": "up", "left": "left", "right": "right", "aage": "down", "peeche": "up",
              "neeche_kar": "down", "upar_kar": "up", "scroll_down": "down", "scroll_up": "up"}


def scroll_direction(direction):
    """'neeche scroll karo' jaisi baat ko 'down'/'up'/'left'/'right' mein badal do (validate bhi)."""
    a = re.sub(r"[^a-z]+", "_", _norm(direction)).strip("_")
    a = _DIR_WORDS.get(a, a)
    if a not in DIRECTIONS:
        raise PhoneError("Scroll direction: down (neeche), up (upar), left ya right, sir.")
    return a


def swipe(direction):
    """Screen ko ek haath ki safar jaisa scroll karo. direction = content kis taraf jayega:
    'down' = neeche ka content (ungli upar), 'up' = upar ka content, 'left'/'right' = side."""
    d = scroll_direction(direction)
    ensure()
    dump = _shell("dumpsys", "window")
    guard_screen(dump)
    guard_foreground(dump)
    w, h = screen_size()
    cx, cy = w // 2, h // 2
    far_x, far_y = int(w * 0.75), int(h * 0.75)
    near_x, near_y = int(w * 0.25), int(h * 0.25)
    moves = {"down": (cx, far_y, cx, near_y), "up": (cx, near_y, cx, far_y),
             "left": (far_x, cy, near_x, cy), "right": (near_x, cy, far_x, cy)}
    x1, y1, x2, y2 = moves[d]
    _shell("input", "swipe", str(x1), str(y1), str(x2), str(y2), "300")
    return d
