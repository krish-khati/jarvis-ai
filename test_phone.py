# Phone tools ka test - DRY_RUN=1, nakli adb (phone._adb). Asli phone/adb kabhi nahi chalta.
#   DRY_RUN=1 ./venv/Scripts/python.exe test_phone.py
import os
os.environ["DRY_RUN"] = "1"
os.environ["PHONE_ADB_ADDRESS"] = "192.168.1.50:37123"
os.environ["BRIEFING_CITY"] = "Kaithal"

import brain
import permissions
import phone
import tools

fails = 0


def check(name, cond):
    global fails
    print(("OK   " if cond else "FAIL ") + name)
    fails += not cond


calls, connected = [], [True]
PKGS = "\n".join("package:" + p for p in ["com.whatsapp", "com.google.android.youtube", "com.phonepe.app",
                                          "com.android.settings", "com.instagram.android",
                                          "com.sec.android.app.camera", "com.android.dialer"])
FOCUS = ["com.whatsapp"]


def fake_adb(args, binary=False, timeout=8):
    calls.append(args)
    if not connected[0]:
        raise phone.PhoneError(phone.NOT_CONNECTED)
    cmd = " ".join(args)
    if "dumpsys battery" in cmd:
        return "  AC powered: false\n  USB powered: true\n  level: 73\n"
    if "pm list packages" in cmd:
        return PKGS
    if "dumpsys window" in cmd:
        return "mCurrentFocus=Window{abc u0 %s/com.x.Main}" % FOCUS[0]
    if "wm size" in cmd:
        return "Physical size: 1080x2400"
    if "screencap" in cmd:
        return b"\x89PNG\r\n" + b"0" * 20
    return "ok"


phone._adb = fake_adb


def acted():   # koi asli kaam (launch/input) chala?
    return [c for c in calls if any(w in c for w in ("monkey", "input"))]


def run(fn, request, *a, **k):
    tools.current_request = request
    try:
        return "RESULT " + str(fn(*a, **k))
    except tools.DirectReply as d:
        return d.reply


asked = []


def say(ans):
    def c(q):
        asked.append(q)
        return ans
    tools.confirm = c


# --- tools ki ginti / risk ---
names = {f.__name__ for f in tools.ALL_TOOLS}
check("52 tools, risk table match", len(names) == 52 and names == set(permissions.RISK))
check("brain copy same", set(brain.TOOLS_BY_NAME) == names)
check("phone SAFE 2 / CONFIRM 6",
      all(permissions.risk(n) == "SAFE" for n in ("phone_status", "phone_screenshot"))
      and all(permissions.risk(n) == "CONFIRM" for n in ("phone_open_app", "phone_type", "phone_tap",
                                                          "phone_back", "phone_home", "phone_media")))
check("NEVER tool banaya hi nahi",
      not [n for n in names if n.startswith("phone_")
           and any(w in n for w in ("install", "delete", "sms", "call", "shell", "adb", "settings", "reset", "pay"))])

# --- status ---
check("status connected", "73%" in run(tools.phone_status, "phone ki battery batao")
      and "charge ho raha" in run(tools.phone_status, "phone status"))
connected[0] = False
check("disconnect message", "connected nahi hai, Wireless debugging on karo" in run(tools.phone_status, "phone ki battery"))
connected[0] = True

# --- safety lock ---
calls.clear()
check("lock: phone word nahi = BLOCKED", "BLOCKED" in run(tools.phone_status, "battery batao") and not calls)

# --- open_app confirm ---
calls.clear(); asked.clear(); say(False)
r = run(tools.phone_open_app, "phone pe whatsapp kholo", "whatsapp")
check("open_app: confirm poochha, nahi = kuch nahi", len(asked) == 1 and "nahi kiya" in r and not acted())
say(True)
r = run(tools.phone_open_app, "phone pe whatsapp kholo", "whatsapp")
check("open_app: haan + DRY_RUN = launch nahi", "Test mode" in r and not acted())
for bad in ("phonepe", "settings", "paytm", "dialer"):
    calls.clear(); asked.clear()
    r = run(tools.phone_open_app, "phone pe kholo", bad)
    check(f"open_app {bad}: refuse, confirm bhi nahi", not asked and not acted() and not r.startswith("RESULT"))
check("open_app: anjaan app", "nahi mila" in run(tools.phone_open_app, "phone pe kholo", "nonexistentapp"))
check("resolve: alias", phone.resolve_app("whatsapp") == ("com.whatsapp", None)
      and phone.resolve_app("Instagram")[0] == "com.instagram.android")
check("is_blocked", phone.is_blocked("com.phonepe.app") and phone.is_blocked("com.android.settings")
      and not phone.is_blocked("com.whatsapp"))

# --- type / tap / back / home / media: confirm + DRY ---
for fn, args, req in ((tools.phone_type, ("hello there",), "phone mein type karo hello there"),
                      (tools.phone_tap, (100, 200), "phone pe tap karo"),
                      (tools.phone_back, (), "phone back"), (tools.phone_home, (), "phone home"),
                      (tools.phone_media, ("pause",), "phone pe music pause")):
    calls.clear(); asked.clear(); say(False)
    r1 = run(fn, req, *args)
    say(True)
    r2 = run(fn, req, *args)
    check(f"{fn.__name__}: confirm + DRY_RUN", "nahi kiya" in r1 and "Test mode" in r2 and not acted() and len(asked) == 2)
asked.clear()
check("type: bura text (shell chars) refuse, confirm bhi nahi",
      "sirf English" in run(tools.phone_type, "phone type", "a; rm -rf /") and not asked)

# --- asli chalne wale phone.* functions (fake adb) ---
calls.clear(); phone.type_text("hi there")
check("type_text: %s space, fixed args", calls[-1][-3:] == ["input", "text", "hi%sthere"])
calls.clear(); phone.tap(10, 20)
check("tap sahi", calls[-1][-3:] == ["tap", "10", "20"])
try:
    phone.tap(5000, 5)
    check("tap bahar = error", False)
except phone.PhoneError:
    check("tap bahar = error", True)
calls.clear(); phone.media("volume badhao"); phone.media("next")
check("media keys", [c[-1] for c in calls if "keyevent" in c] == ["24", "87"])
try:
    phone.media("rm -rf")
    check("media anjaan = error", False)
except phone.PhoneError:
    check("media anjaan = error", True)
FOCUS[0] = "com.phonepe.app"
for label, f in (("type", lambda: phone.type_text("x")), ("tap", lambda: phone.tap(1, 1)),
                 ("back", lambda: phone.key("back"))):
    try:
        f()
        check(f"payment app foreground: {label} band", False)
    except phone.PhoneError:
        check(f"payment app foreground: {label} band", True)
FOCUS[0] = "com.whatsapp"

# --- screenshot (RAM, UNTRUSTED) ---
tools.phone_last_image = None
check("screenshot", "HUD pe" in run(tools.phone_screenshot, "phone ka screenshot")
      and tools.phone_last_image.startswith(b"\x89PNG"))
check("screenshot untrusted + incoming", "phone_screenshot" in permissions.UNTRUSTED_SOURCES
      and "phone_screenshot" in permissions.INCOMING_MESSAGE_TOOLS)

# --- address: sirf ghar ka WiFi ---
for addr, ok in (("192.168.1.5:5555", True), ("10.0.0.2:4000", True), ("8.8.8.8:5555", False),
                 ("127.0.0.1:5555", False), ("junk", False), ("", False)):
    os.environ["PHONE_ADB_ADDRESS"] = addr
    check(f"address {addr or 'khali'} -> {ok}", bool(phone.address()) == ok)
os.environ["PHONE_ADB_ADDRESS"] = "192.168.1.50:37123"

# --- Telegram se: SAFE chalta hai, CONFIRM Telegram ke buttons (tools.confirm hook) se ---
tools.source = "telegram"; asked.clear(); say(True)
check("telegram: SAFE status", "73%" in run(tools.phone_status, "phone ki battery"))
run(tools.phone_back, "phone back")
check("telegram: CONFIRM tool confirm hook se poochta hai", len(asked) == 1)
tools.source = ""

# --- Agent Guard ---
g = permissions.Guard(confirm=lambda q: True)
tools.current_request = "phone ki battery batao"
st, txt = g.run("phone_status")
check("guard: SAFE phone tool", st == "ok" and "73%" in txt)
tools.current_request = "phone back"
calls.clear()
st, txt = permissions.Guard(confirm=lambda q: True).run("phone_back")
check("guard: CONFIRM phone tool (apna confirm) DRY_RUN, asli kaam nahi", "Test mode" in txt and not acted())
g3 = permissions.Guard(confirm=lambda q: True)
tools.current_request = "phone screen dekho"
g3.run("phone_screenshot")
tools.current_request = "phone back"
check("guard: phone screen dekhne ke baad action block", g3.run("phone_back")[0] == "blocked")

# --- get_weather default city ---
import httpx
seen = {}


class R:
    def __init__(s, d):
        s.d = d

    def json(s):
        return s.d


def fake_get(url, params=None, timeout=0):
    if "geocoding" in url:
        seen["city"] = params["name"]
        return R({"results": [{"name": "Kaithal", "latitude": 29.8, "longitude": 76.4}]})
    return R({"current": {"temperature_2m": 30, "apparent_temperature": 31, "relative_humidity_2m": 40,
                          "weather_code": 0, "wind_speed_10m": 5},
              "daily": {"temperature_2m_max": [34], "temperature_2m_min": [24], "precipitation_probability_max": [10]}})


httpx.get = fake_get
tools.current_request = "mausam batao"
tools.get_weather("")
check("weather: shahar khali = BRIEFING_CITY", seen.get("city") == "Kaithal")
check("groq schema: city required nahi", brain._SCHEMA_BY_NAME["get_weather"]["function"]["parameters"]["required"] == [])

print("\nFAILS:", fails)
raise SystemExit(1 if fails else 0)
