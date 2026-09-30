# ============================================
# scheduler.py - reminders / tasks (tasks.json) + Hinglish time parser
#   "10 minute baad yaad dilana ki paani peena hai", "kal subah 7 baje weather batana",
#   "har roz raat 10 baje sone ki yaad dilana".
#   Time samajh na aaye to andaza NAHI lagate - poochte hain (parse_request "ask" deta hai).
#   Ek hi background thread har CHECK_SECONDS mein tasks dekhta hai. Awake ho to task
#   `due` mein jaata hai (main.py voice thread bolta hai); sleep mein ho to hooks["sleep"]
#   (halka chime + chhota notification) - JARVIS jagta nahi, window fullscreen nahi hoti.
# ============================================

import datetime
import json
import os
import re
import threading
import time

TASKS_FILE = os.getenv("JARVIS_TASKS_FILE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.json")
CHECK_SECONDS = 20        # Itne second mein ek baar tasks dekho
LATE_LIMIT = 600          # Time se itna (10 min) zyada late ho gaya to "miss ho gaya" (PC band tha)

awake = False             # main.py set karta hai: JARVIS abhi jaag raha hai?
hooks = {"sleep": None, "briefing": None}   # sleep mein reminder: hooks["sleep"](task); briefing: hooks["briefing"]()
due = []                  # Awake mein aaye tasks - main.py ki voice thread inhe bolti hai
missed = []               # Band/sleep-PC ke dauran chhoot gaye reminders (jagne pe batate hain)
last_fired = None         # Aakhri baja hua reminder ("snooze" isi ka hota hai)
briefing_pending = False  # Morning briefing ka time aa chuka, abhi boli nahi gayi (main.py bolta hai)
BRIEFING_GRACE = 3 * 3600  # BRIEFING_TIME se itna (3 ghante) zyada late start ho to us din briefing chhod do
BRIEFING_STATE = os.path.join(os.path.dirname(TASKS_FILE), "briefing_state.json")  # Aakhri briefing ki tareekh
_lock = threading.RLock()
_thread = None


# ============================================
# 1. HINGLISH TIME PARSER (khud ka, chhota)
# ============================================
NUM_WORDS = {"ek": 1, "one": 1, "do": 2, "two": 2, "teen": 3, "three": 3, "char": 4, "chaar": 4, "four": 4,
             "paanch": 5, "panch": 5, "five": 5, "chhe": 6, "chhah": 6, "six": 6, "saat": 7, "seven": 7,
             "aath": 8, "eight": 8, "nau": 9, "nine": 9, "das": 10, "ten": 10, "gyarah": 11, "eleven": 11,
             "barah": 12, "twelve": 12, "pandrah": 15, "fifteen": 15, "bees": 20, "twenty": 20,
             "tees": 30, "thirty": 30, "chalis": 40, "pachaas": 50, "pachas": 50}
_NUM = r"(?:\d+|" + "|".join(sorted(NUM_WORDS, key=len, reverse=True)) + r")"
_UNIT = r"(?:seconds?|secs?|minutes?|mins?|ghanta|ghante|ghantey|hours?|hrs?)"
_SPECIAL_DUR = re.compile(r"\b(?:(?P<dedh>dedh)|(?P<dhai>dhai|dhaai)|(?P<half>aadha|aadhe|half))"
                          r" (?:ghanta|ghante|ghantey|hour)(?: (?:baad|mein|me|later))?\b", re.I)
_DUR = re.compile(rf"\b(?:(?:in|after) (?P<n1>{_NUM}) (?P<u1>{_UNIT})|"
                  rf"(?P<n2>{_NUM}) (?P<u2>{_UNIT}) (?:baad|mein|me|later))\b", re.I)
_DAY = re.compile(r"\b(aaj|today|kal|tomorrow|parso|parson|day after tomorrow)\b", re.I)
_PART = re.compile(r"\b(subah|savere|morning|dopahar|dophar|dupahar|afternoon|shaam|sham|evening|"
                   r"raat|rat|night)\b", re.I)
_CLOCK_HM = re.compile(r"\b(?P<h>\d{1,2}):(?P<m>\d{2})(?:\s*(?P<ap>am|pm))?(?:\s+baje)?\b", re.I)
_CLOCK_FRAC = re.compile(rf"\b(?P<pre>sadhe|saade|sade|sawa|savva|paune) (?P<h>{_NUM})(?: baje)?\b", re.I)
_CLOCK_AP = re.compile(rf"\b(?P<h>{_NUM})\s*(?P<ap>am|pm)\b", re.I)
_CLOCK_BAJE = re.compile(rf"\b(?P<h>{_NUM}) baje\b", re.I)
_REPEAT_D = re.compile(r"\b(har roz|rozana|roz|daily|every day|har din|hamesha)\b", re.I)
_REPEAT_W = re.compile(r"\b(har hafte|weekly|every week|hafte mein ek baar)\b", re.I)
_MARKER = re.compile(r"\b(yaad dila dena|yaad dilana|yaad dilao|yaad dilaana|yaad dila do|yaad dila|"
                     r"remind me to|remind me that|remind me|reminder)\b", re.I)
_TASK_VERB = re.compile(r"\b(batana|batao|karna|kar dena|dena|bhejna|kholna|chalana|sunana|dikhana|padhna)\s*$",
                        re.I)
_STRIP_EDGE = {"ko", "par", "pe", "tak", "ki", "ka", "ke", "baad", "mein", "me", "please", "to", "that",
               "aur", "then", "phir"}
WEEKDAYS = ["somvar", "mangalvar", "budhvar", "guruvar", "shukravar", "shanivar", "ravivar"]


def _val(s):
    s = s.lower()
    return float(s) if re.fullmatch(r"\d+(?:\.\d+)?", s) else float(NUM_WORDS[s])


def _cut(text, m):
    """text se match wala hissa hata do."""
    return text[:m.start()] + " " + text[m.end():]


def _to24(h, part, ap):
    """Ghante ko 24h mein badlo (part = subah/dopahar/shaam/raat ya None). None = samajh nahi aaya."""
    if ap:
        if not 1 <= h <= 12:
            return None
        return h % 12 + (12 if ap == "pm" else 0)
    if h > 12:
        return h if h <= 23 and not part else None
    if h == 0:
        return 0
    if part == "subah":
        return h if h < 12 else None
    if part == "dopahar":
        return 12 if h == 12 else (h + 12 if h <= 5 else None)
    if part == "shaam":
        return h + 12 if h <= 11 else None
    if part == "raat":
        return 0 if h == 12 else (h + 12 if h >= 6 else h)
    return "ask"              # subah/shaam ka pata nahi - poochna padega


def _part_name(word):
    w = word.lower()
    if w in ("subah", "savere", "morning"):
        return "subah"
    if w in ("dopahar", "dophar", "dupahar", "afternoon"):
        return "dopahar"
    if w in ("shaam", "sham", "evening"):
        return "shaam"
    return "raat"


def _clock_words(dt):
    """Ghante ka Hinglish roop: 7 -> 'subah 7 baje', 18:30 -> 'shaam 6:30 baje'."""
    h = dt.hour
    part = "subah" if 4 <= h < 12 else "dopahar" if 12 <= h < 16 else "shaam" if 16 <= h < 20 else "raat"
    h12 = h % 12 or 12
    return f"{part} {h12}{':%02d' % dt.minute if dt.minute else ''} baje"


def parse_duration(text):
    """'10 minute baad' / 'dedh ghante baad' / 'aadha ghanta' -> minutes (float) ya None."""
    m = _SPECIAL_DUR.search(text)
    if m:
        return 90.0 if m["dedh"] else 150.0 if m["dhai"] else 30.0
    m = _DUR.search(text)
    if not m:
        return None
    n, u = _val(m["n1"] or m["n2"]), (m["u1"] or m["u2"]).lower()
    if u.startswith("sec"):
        return n / 60
    return n * (60 if u.startswith(("gh", "h")) else 1)


def _duration_label(minutes):
    if minutes < 1:
        return f"{round(minutes * 60)} second baad"
    if minutes < 60:
        return f"{minutes:g} minute baad"
    h, m = divmod(round(minutes), 60)
    return f"{h} ghante baad" if not m else f"{h} ghante {m} minute baad"


def parse_request(text, now=None):
    """Poora command ("... yaad dilana ...") -> ek jawab:
       ("ok", {"when": datetime, "what": str, "repeat": "none/daily/weekly", "kind": "remind/act",
               "label": "kal subah 7 baje"})
       ("ask", sawaal)   time/kaam adhoora - user se poochho, jawab text ke peeche jodke dobara parse karo
       ("fail", wajah)   samajh nahi aaya (andaza nahi lagate)"""
    now = now or datetime.datetime.now()
    rest = " ".join(str(text or "").replace("।", " ").replace("?", " ").replace("!", " ").split())
    repeat = "none"
    if _REPEAT_W.search(rest):
        repeat, rest = "weekly", _cut(rest, _REPEAT_W.search(rest))
    elif _REPEAT_D.search(rest):
        repeat, rest = "daily", _cut(rest, _REPEAT_D.search(rest))
    mark = _MARKER.search(rest)
    kind = "remind" if mark else "act"
    if mark:
        rest = _cut(rest, mark)

    when, label = None, None
    minutes = parse_duration(rest)
    if minutes is not None:
        if repeat != "none":
            return ("fail", "har roz/hafte ke saath baje wala time bolo")
        m = _SPECIAL_DUR.search(rest) or _DUR.search(rest)
        rest = _cut(rest, m)
        when = now + datetime.timedelta(minutes=minutes)
        label = _duration_label(minutes)
    else:
        if re.search(r"\bbaad\b", rest, re.I) and not re.search(r"\bbaje\b", rest, re.I):
            return ("fail", "kitne minute/ghante baad, ye samajh nahi aaya")
        day = _DAY.search(rest)
        if day:
            rest = _cut(rest, day)
        part = _PART.search(rest)
        if part:
            rest = _cut(rest, part)
        h = mnt = ap = None
        for rx in (_CLOCK_HM, _CLOCK_FRAC, _CLOCK_AP, _CLOCK_BAJE):
            m = rx.search(rest)
            if not m:
                continue
            g = m.groupdict()
            h = int(g["h"]) if g["h"].isdigit() else int(_val(g["h"]))
            mnt = int(g["m"]) if g.get("m") else 0
            ap = (g.get("ap") or "").lower() or None
            pre = (g.get("pre") or "").lower()
            if pre in ("sadhe", "saade", "sade"):
                mnt = 30
            elif pre in ("sawa", "savva"):
                mnt = 15
            elif pre == "paune":
                h, mnt = h - 1, 45
            rest = _cut(rest, m)
            break
        pname = _part_name(part[1]) if part else None
        if h is None:
            if day or part:
                what_q = f"{day[1].lower() if day else ''} {pname or ''}".strip()
                return ("ask", f"{what_q.capitalize()} kitne baje, sir?")
            return ("fail", "time nahi mila")
        h24 = _to24(h, pname, ap)
        if h24 == "ask":
            return ("ask", f"{h} baje subah ya shaam, sir?")
        if h24 is None or not 0 <= mnt <= 59:
            return ("fail", "ye time sahi nahi lag raha")
        dword = day[1].lower() if day else None
        add = {"kal": 1, "tomorrow": 1, "parso": 2, "parson": 2, "day after tomorrow": 2}.get(dword, 0)
        when = (now + datetime.timedelta(days=add)).replace(hour=h24, minute=mnt, second=0, microsecond=0)
        if when <= now:
            if dword in ("aaj", "today"):
                return ("fail", "wo time nikal chuka hai")
            if add == 0:
                when += datetime.timedelta(days=1)       # Baje wala time aaj nikal gaya -> agla din
        days = (when.date() - now.date()).days
        clock = _clock_words(when)
        if repeat == "daily":
            label = f"har roz {clock}"
        elif repeat == "weekly":
            label = f"har {WEEKDAYS[when.weekday()]} {clock}"
        else:
            label = ("aaj " if days == 0 else "kal " if days == 1 else "parso " if days == 2
                     else when.strftime("%d %b ")) + clock

    # Kaam ka text: bache hue shabd, aage-peeche ke faltu shabd hatao
    words = rest.split()
    while words and words[0].lower() in _STRIP_EDGE:
        words.pop(0)
    while words and words[-1].lower() in _STRIP_EDGE:
        if words[-1].lower() in ("ki", "ka", "ke") and mark and len(words) >= 2:
            words.append("yaad")          # "sone ki yaad dilana" -> "sone ki yaad"
            break
        words.pop()
    what = " ".join(words).strip(" :,-")
    if not what:
        return ("ask", "Kis baare mein yaad dilaun, sir?")
    return ("ok", {"when": when, "what": what, "repeat": repeat, "kind": kind, "label": label})


def looks_like_reminder(text):
    """Bina AI shortcut ke liye: ye command reminder banane ka hai? (sirf pakka pehchan pe True)
    - "yaad dilana / remind me / reminder" shabd ho, YA
    - koi pakka time ("N minute baad", "7 baje", "7 pm", "7:30") aur aakhir mein kaam wala "-na" shabd."""
    t = str(text or "").lower()
    if re.search(r"\b(kya|kaun|kab|kaise|kyun|what|when|why|how)\b", t) and not _MARKER.search(t):
        return False
    if _MARKER.search(t):
        return bool(_DAY.search(t) or _PART.search(t) or parse_duration(t) is not None
                    or _CLOCK_BAJE.search(t) or _CLOCK_AP.search(t) or _CLOCK_HM.search(t)
                    or _CLOCK_FRAC.search(t) or _REPEAT_D.search(t) or _REPEAT_W.search(t))
    firm = (parse_duration(t) is not None or _CLOCK_BAJE.search(t) or _CLOCK_AP.search(t)
            or _CLOCK_HM.search(t) or _CLOCK_FRAC.search(t))
    return bool(firm and _TASK_VERB.search(t))


# ============================================
# 2. tasks.json (id, when, what, repeat, kind)
# ============================================
def _load():
    """tasks.json padho. Na ho to []. Kharab ho to error (overwrite nahi - tasks na jayein)."""
    try:
        with open(TASKS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        raise ValueError("tasks.json kharab ho gayi hai - VS Code mein theek karo")


def _save(tasks):
    """Temp file mein likho phir badlo - beech mein band ho to bhi purane tasks bache rahein."""
    tmp = TASKS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TASKS_FILE)


def all_tasks():
    """Time ke hisaab se sorted (numbering yahi hai: 'task 2 hata do')."""
    with _lock:
        return sorted(_load(), key=lambda t: t["when"])


def add(when, what, repeat="none", kind="remind"):
    with _lock:
        tasks = _load()
        tid = max([t["id"] for t in tasks], default=0) + 1
        tasks.append({"id": tid, "when": when.strftime("%Y-%m-%dT%H:%M:%S"), "what": what,
                      "repeat": repeat, "kind": kind})
        _save(tasks)
        return tid


def remove_number(number):
    """all_tasks() ke number se hatao. True = hataya."""
    with _lock:
        ordered = all_tasks()
        if not 1 <= number <= len(ordered):
            return False
        gone = ordered[number - 1]["id"]
        _save([t for t in _load() if t["id"] != gone])
        return True


def clear():
    with _lock:
        n = len(_load())
        _save([])
        return n


def describe(task):
    """Ek task ka bolne layak roop: 'kal subah 7 baje: weather batana'."""
    when = datetime.datetime.fromisoformat(task["when"])
    now = datetime.datetime.now()
    days = (when.date() - now.date()).days
    clock = _clock_words(when)
    if task["repeat"] == "daily":
        label = f"har roz {clock}"
    elif task["repeat"] == "weekly":
        label = f"har {WEEKDAYS[when.weekday()]} {clock}"
    else:
        label = ("aaj " if days == 0 else "kal " if days == 1 else when.strftime("%d %b ")) + clock
    return f"{label}: {task['what']}"


# ============================================
# 3. CHECK LOOP (ek background thread)
# ============================================
def _advance(task, now):
    """Baja hua/chhoota task: repeat ho to agli baari par, warna file se hata do. (_lock ke andar)"""
    tasks = _load()
    if task["repeat"] == "none":
        tasks = [t for t in tasks if t["id"] != task["id"]]
    else:
        step = datetime.timedelta(days=1 if task["repeat"] == "daily" else 7)
        for t in tasks:
            if t["id"] == task["id"]:
                when = datetime.datetime.fromisoformat(t["when"])
                while when <= now:
                    when += step
                t["when"] = when.strftime("%Y-%m-%dT%H:%M:%S")
    _save(tasks)


def check(now=None, startup=False):
    """Jo tasks ka time aa gaya unhe fire karo (thread har CHECK_SECONDS mein bulata hai).
    LATE_LIMIT se zyada late (ya startup pe koi bhi late) = 'miss ho gaya' - fire nahi, missed list mein."""
    global last_fired
    now = now or datetime.datetime.now()
    fire_now = []
    with _lock:
        for t in _load():
            when = datetime.datetime.fromisoformat(t["when"])
            if when > now:
                continue
            (missed if startup or (now - when).total_seconds() > LATE_LIMIT else fire_now).append(t)
            _advance(t, now)
        if fire_now:
            last_fired = fire_now[-1]
    for t in fire_now:
        if awake:
            with _lock:
                due.append(t)                   # main.py ki voice thread bolegi
        elif hooks["sleep"]:
            try:
                hooks["sleep"](t)               # Sleep mein: chime + chhota notification, bas
            except Exception:
                pass
    return fire_now


def pop_due():
    with _lock:
        items, due[:] = list(due), []
        return items


def pop_missed():
    with _lock:
        items, missed[:] = list(missed), []
        return items


def snooze(minutes=10):
    """Aakhri baje reminder ko minutes baad phir. False = koi reminder aaya hi nahi."""
    if not last_fired:
        return False
    add(datetime.datetime.now() + datetime.timedelta(minutes=minutes), last_fired["what"], "none",
        last_fired.get("kind", "remind"))
    return True


# ============================================
# 4. MORNING BRIEFING (.env BRIEFING_TIME=07:30, khali = band)
#   Din mein ek baar. Awake ho to `briefing_pending` (main.py voice thread bolti hai), sleep mein ho to
#   hooks["briefing"] (chime + HUD notification) aur poori briefing "Hey Jarvis" pe. Tareekh file mein
#   rehti hai, isliye restart pe dobara nahi bajti.
# ============================================
def briefing_time():
    """.env BRIEFING_TIME ("07:30") -> datetime.time, ya None (khali / galat = band)."""
    raw = os.getenv("BRIEFING_TIME", "").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
    if m and int(m[1]) < 24 and int(m[2]) < 60:
        return datetime.time(int(m[1]), int(m[2]))
    return None


def _briefing_done_today(today):
    try:
        with open(BRIEFING_STATE, encoding="utf-8") as f:
            return json.load(f).get("date") == today
    except (OSError, ValueError):
        return False


def _briefing_mark(today):
    try:
        with open(BRIEFING_STATE, "w", encoding="utf-8") as f:
            json.dump({"date": today}, f)
    except OSError:
        pass


def check_briefing(now=None):
    """Briefing ka time aa gaya (aur aaj abhi tak nahi hui) to trigger karo. True = trigger hua."""
    global briefing_pending
    at = briefing_time()
    if not at:
        return False
    now = now or datetime.datetime.now()
    today = now.date().isoformat()
    target = datetime.datetime.combine(now.date(), at)
    if now < target or _briefing_done_today(today):
        return False
    _briefing_mark(today)                       # Ek din mein ek baar (late start pe bhi)
    if (now - target).total_seconds() > BRIEFING_GRACE:
        return False                            # Bahut late (PC dopahar ko chala) - aaj chhod do
    with _lock:
        briefing_pending = True
    if not awake and hooks["briefing"]:
        try:
            hooks["briefing"]()                 # Sleep mein: chime + notification, JARVIS jagta nahi
        except Exception:
            pass
    return True


def pop_briefing():
    """True agar briefing bolni baaki hai (aur flag saaf kar deta hai)."""
    global briefing_pending
    with _lock:
        was, briefing_pending = briefing_pending, False
        return was


def _loop():
    while True:
        try:
            check()
        except Exception:
            pass                                # Thread kabhi na mare
        try:
            check_briefing()
        except Exception:
            pass
        time.sleep(CHECK_SECONDS)


def start():
    """Ek hi background thread. Pehle startup check: band rehne ke dauran jo chhoot gaye wo missed."""
    global _thread
    if _thread is not None:
        return
    try:
        check(startup=True)     # Band rehte waqt jo nikal gaye -> missed (main wake pe batata hai)
    except Exception:
        pass
    try:
        check_briefing()        # Subah start hua aur briefing ka time nikal chuka ho
    except Exception:
        pass
    _thread = threading.Thread(target=_loop, daemon=True, name="scheduler")
    _thread.start()
