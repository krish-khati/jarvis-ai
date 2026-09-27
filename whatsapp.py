# ============================================
# whatsapp.py - WhatsApp Desktop ko "insaan ki tarah" chalana (koi number file nahi)
#   1. WhatsApp kholo/saamne lao
#   2. Search box mein naam likho, results padho (sirf "Chats"/"Contacts", "Messages" wale nahi)
#   3. 1 result -> kholo | kai results -> Krish se poochho | 0 -> kuch nahi
#   4. Chat khulne pe header ("Type a message to <naam>") PADHO - wahi naam confirm hota hai
#   5. Message: clipboard se paste (Hindi/emoji) + Enter, phir check ki chat mein dikha
#   6. Call: header ke Voice/Video call button
# Koi unofficial WhatsApp library nahi (ban ka risk nahi) - sirf official app ka UI.
# WhatsApp Desktop andar se WhatsApp Web (WebView2) hai; ye naam usi ke UI labels hain.
# ============================================

import difflib
import os
import re
import time

import ui

APP_ID = r"shell:AppsFolder\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"
SEARCH_BOX = "Search or start a new chat"
RESULTS_GRID = "Search results."
MESSAGE_BOX = re.compile(r"^Type a message to (?P<name>.+)$")
RESULTS_WAIT = 2.5          # Search ke baad results aane ka intezaar
CHAT_OPEN_WAIT = 2.0        # Result pe click ke baad chat khulne ka intezaar

VOICE_CALL = re.compile(r"(?i)^(voice call|audio call)$")
VIDEO_CALL = re.compile(r"(?i)^video call$")
CALL_MENU = re.compile(r"(?i)^(call|calls|start call|call options)$")
END_CALL = re.compile(r"(?i)^(end call|hang ?up|leave call|leave)$")
# Results list ke section headers - "Messages" wale results kisi message ke ANDAR ke text
# ke match hote hain, wo contact nahi hain (unhe chhod dete hain)
CHAT_SECTIONS = {"chats", "contacts", "groups", "contacts on whatsapp", "other contacts", "not in your contacts"}
SKIP_SECTIONS = {"messages"}
_DATE_TAIL = re.compile(r"\s+(\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}:\d{2}(\s?[ap]\.?m\.?)?|yesterday|today|"
                        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", re.IGNORECASE)
SELF_QUERY = "You"          # Apni chat "+91 ... (You)" - "You" search karne pe milti hai
CHAT_LIST = "Chat list"    # Left side ki chat list (apni "(You)" chat isme sabse upar pinned)
MAX_OPEN_TRIES = 2         # Chat kholne ki max koshish - kabhi bina limit ke retry nahi

_step_ids = iter(range(1, 10**9))


def mask(text):
    """Naam mein phone number ho (unsaved contact / apni chat) to sirf aakhri 4 ank: "***1154" """
    return re.sub(r"\+?\d[\d \-]{6,}\d", lambda m: "***" + re.sub(r"\D", "", m.group(0))[-4:], text or "")


def step(title, detail, status, sid=None):
    """UI Activity card (Searching Rahul -> Chat opened -> Sent). sid dene pe wahi card update."""
    sid = sid or f"wa-{next(_step_ids)}"
    ui.action(sid, title, mask(detail), status)
    return sid


# ---------------- Window / elements ----------------
_cache = {"win": None, "doc": None, "doc_for": None}   # Window aur page ek baar dhoondh ke yaad


def _alive(wrapper):
    """Cached element abhi bhi zinda hai? (Window band / page reload hua to exception)"""
    try:
        wrapper.element_info.element.CurrentBoundingRectangle
        return wrapper.element_info.element.CurrentProcessId != 0
    except Exception:
        return False


def _is_wa(w):
    return w.class_name() == "WinUIDesktopWin32WindowClass" and re.search(r"(?i)\bwhatsapp$", w.window_text() or "")


def _window():
    """WhatsApp kholo (band/tray mein ho to bhi) aur main window ka wrapper do.
    Title "(10) WhatsApp" jaisa hota hai - unread ginti aage lagti hai.
    Window cached: pehle se khuli + dikh rahi ho to startfile/scan nahi (bas focus)."""
    from pywinauto import Desktop
    w = _cache["win"]
    try:
        if w is not None and _alive(w) and w.is_visible() and _is_wa(w):
            if w.is_minimized():
                w.restore()
            w.set_focus()
            return w
    except Exception:
        pass
    _cache["win"] = None
    os.startfile(APP_ID)                 # Tray mein chhupi ho to bhi saamne aati hai
    deadline = time.time() + 20
    while time.time() < deadline:
        for w in Desktop(backend="uia").windows():
            try:
                if _is_wa(w):
                    if w.is_minimized():
                        w.restore()
                    w.set_focus()
                    _cache["win"] = w
                    return w
            except Exception:
                continue
        time.sleep(0.3)
    raise RuntimeError("WhatsApp Desktop ki window nahi khuli (install/login hai?)")


def _doc(win, timeout=10):
    """WebView ka page (Document "RootWebArea"). Native UIA FindFirst se ~0.05s -
    pywinauto descendants()/child_window() se ye ~6s leta tha (search 20+ second ka tha).
    Page cached rehta hai; window badli ya page reload hua to dobara dhoondhte hain."""
    from pywinauto.controls.uiawrapper import UIAWrapper
    from pywinauto.uia_defines import IUIA
    from pywinauto.uia_element_info import UIAElementInfo
    doc = _cache["doc"]
    if doc is not None and _cache["doc_for"] == win.handle and _alive(doc):
        return doc
    iuia = IUIA()
    cond = iuia.iuia.CreatePropertyCondition(iuia.UIA_dll.UIA_AutomationIdPropertyId, "RootWebArea")
    deadline = time.time() + timeout
    while True:
        try:
            el = win.element_info.element.FindFirst(iuia.tree_scope["descendants"], cond)
            if el:
                doc = UIAWrapper(UIAElementInfo(el))
                _cache.update(doc=doc, doc_for=win.handle)
                return doc
        except Exception:
            pass
        if time.time() > deadline:
            raise RuntimeError("WhatsApp ka page (RootWebArea) nahi mila")
        time.sleep(0.3)                  # App abhi khul rahi hai - page load hone do


def _paste(text):
    """Clipboard se paste - Hindi aur emoji bhi sahi jaate hain (typing se toot jaate)."""
    import pyperclip
    from pywinauto.keyboard import send_keys
    old = None
    try:
        old = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(text)
    send_keys("^v")
    time.sleep(0.3)
    if old is not None:
        try:
            pyperclip.copy(old)          # Krish ka purana clipboard wapas
        except Exception:
            pass


def log(step_name, t0, ok, extra=""):
    """Terminal mein har step ka time aur result (naam/number nahi - sirf step + ginti)."""
    print(f"[WA] {step_name:<24} {time.time() - t0:5.2f}s  {'OK' if ok else 'FAIL'} {extra}".rstrip())
    return ok


def _has_focus(*wrappers):
    """Keyboard focus in me se kisi element pe hai? Paste/Enter se PEHLE ye check hota hai -
    taaki naam galti se message box mein na chala jaaye (pehle "zzqxvjarvis" draft ban gaya tha)."""
    from pywinauto.uia_defines import IUIA
    iuia = IUIA().iuia
    try:
        focused = iuia.GetFocusedElement()
    except Exception:
        return False
    for w in wrappers:
        try:
            if w is not None and iuia.CompareElements(focused, w.element_info.element):
                return True
        except Exception:
            continue
    return False


# ---------------- Search ----------------
def _title_item(row):
    """Row ke andar SIRF "naam + date" wala chhota element (sabse chhota naam).
    Lambe elements (message preview, disappearing-timer ka text) pe kabhi click nahi karte."""
    items = [d for d in row.descendants(control_type="DataItem")
             if d.element_info.name and not d.element_info.name.startswith("View status")]
    return min(items, key=lambda d: len(d.element_info.name)) if items else None


def _result_title(row):
    """Result row se chat ka naam: "naam + date" wale element se date hatao."""
    item = _title_item(row)
    text = item.element_info.name if item else (row.element_info.name or "")
    text = re.sub(r"^View status\s+", "", text).strip()
    return _DATE_TAIL.sub("", text).strip()


def clear_search(win):
    """Search box saaf karke Esc. Keys SIRF tab jab focus pakka search box pe ho -
    warna sirf Esc (message box mein kabhi kuch type nahi hona chahiye)."""
    from pywinauto.keyboard import send_keys
    try:
        box = _search_box(win, timeout=2)
        if not _has_focus(box):
            box.click_input()
            time.sleep(0.15)
        send_keys("^a{BACKSPACE}{ESC}" if _has_focus(box) else "{ESC}")
    except Exception:
        pass


def _search_box(win, timeout=10):
    """Search box dhoondho. Dhyan: box mein text ho to uska naam khaali ho jaata hai
    (naam sirf placeholder "Search or start a new chat" hai) - isliye naam pe bharosa nahi,
    jagah se pehchante hain: jo Edit "Type a message..." nahi hai aur sabse upar hai."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            doc = _doc(win)
            edits = [e for e in doc.descendants(control_type="Edit")
                     if not MESSAGE_BOX.match(e.element_info.name or "")]
            if edits:
                return min(edits, key=lambda e: e.rectangle().top)
        except Exception:
            pass
        time.sleep(0.3)
    raise RuntimeError("WhatsApp ka search box nahi mila")


def search(query):
    """Search box mein naam likho; chat results ki list do: [(title, row_wrapper), ...].
    Naam SIRF tab paste hota hai jab keyboard focus pakka search box pe ho. Ek hi baar
    likhte hain - fail pe search saaf karke khaali list (dobara type nahi)."""
    from pywinauto.keyboard import send_keys
    t = time.time()
    win = _window()
    doc = _doc(win)
    box = _search_box(win, timeout=10)
    log("window + search box", t, True)

    t = time.time()
    box.click_input()
    time.sleep(0.15)
    if not _has_focus(box):
        send_keys("{ESC}")
        log("search box pe focus", t, False, "(kuch type nahi kiya)")
        return win, []
    send_keys("^a{BACKSPACE}")          # Purana text saaf
    _paste(query)
    typed = False
    for _ in range(8):                   # Box mein sahi naam aaya? (max ~1.2s)
        try:
            typed = (box.get_value() or "").strip() == query.strip()
        except Exception:
            typed = False
        if typed:
            break
        time.sleep(0.15)
    log("naam search box mein", t, typed)
    if not typed:
        clear_search(win)
        return win, []

    # Results tabhi lo jab list do baar lagatar same aaye - warna pichle search ke purane
    # results padh lete. Khaali list tabhi maano jab RESULTS_WAIT beet jaaye.
    t = time.time()
    deadline = t + RESULTS_WAIT + 3
    last, results = None, []
    time.sleep(0.5)
    while time.time() < deadline:
        time.sleep(0.3)
        results = _read_results(doc)
        titles = [x for x, _ in results]
        if not titles and time.time() - t < RESULTS_WAIT:
            last = None
            continue
        if last is not None and titles == last:
            break
        last = titles
    else:
        results = []                     # Pakka nahi ho paya -> kuch mat kholo
    log("results", t, bool(results), f"({len(results)} rows)")
    return win, results


def _read_results(doc):
    """Results grid se chat/contact rows padho ("Messages" section wale chhod ke)."""
    try:
        grid = next((g for g in doc.descendants(control_type="DataGrid")
                     if (g.element_info.name or "").strip() == RESULTS_GRID), None)
    except Exception:
        grid = None
    if grid is None:
        return []
    results, section = [], "chats"
    for row in grid.children():
        name = (row.element_info.name or "").strip()
        if name.lower() in CHAT_SECTIONS | SKIP_SECTIONS:
            section = name.lower()
            continue
        if section in SKIP_SECTIONS:
            continue                     # Message ke andar ke text ka match - contact nahi
        title = _result_title(row)
        if title:
            results.append((title, row))
    return results


def _best(results, query, self_chat=False):
    """SIRF wahi results jinke naam mein query ho. Koi na mile to khaali list -
    kabhi koi aur (random) chat nahi kholte."""
    if self_chat:
        return [r for r in results if "(You)" in r[0]]
    q = query.lower().strip()
    return [r for r in results if q in r[0].lower()]


ORDINALS = {"pehla": 0, "pehli": 0, "first": 0, "1": 0, "ek": 0, "doosra": 1, "dusra": 1, "doosri": 1,
            "second": 1, "2": 1, "do": 1, "teesra": 2, "tisra": 2, "third": 2, "3": 2, "teen": 2,
            "chautha": 3, "fourth": 3, "4": 3, "char": 3}


def pick(results, answer):
    """"Kaunsa?" ke jawab se result chuno: naam ("Rahul Gym") ya number ("doosra")."""
    if not answer:
        return None
    a = answer.lower()
    for w in re.findall(r"\w+", a):
        if w in ORDINALS and ORDINALS[w] < len(results):
            return results[ORDINALS[w]]
    titles = [t.lower() for t, _ in results]
    for (t, r) in results:
        extra = t.lower().split()[1:]      # "Rahul Gym" -> "gym"
        if extra and all(x in a for x in extra):
            return (t, r)
    close = difflib.get_close_matches(a, titles, n=1, cutoff=0.5)
    return results[titles.index(close[0])] if close else None


def _norm(name):
    """Naam compare karne ke liye: "(You)" hatao, space/case barabar karo."""
    return re.sub(r"\s+", " ", re.sub(r"\(you\)", "", (name or "").lower())).strip()


def same_chat(header, result_title):
    """Khuli chat ka naam wahi hai jo result chuna tha? (Apni chat ke header mein "(You)" nahi hota.)"""
    h, r = _norm(header), _norm(result_title)
    return bool(h and r) and (h == r or h in r or r in h)


def current_chat(win):
    """Message box "Type a message to <naam>" se khuli chat ka naam + box. Na ho to (None, None)."""
    doc = _doc(win)
    for e in doc.descendants(control_type="Edit"):
        m = MESSAGE_BOX.match(e.element_info.name or "")
        if m:
            return m["name"].strip(), e
    return None, None


def _header_names(win, box):
    """Chat header = message box wale column mein sabse upar ka chauda button (naam wala)."""
    br = box.rectangle()
    names = []
    for b in _doc(win).descendants(control_type="Button"):
        r = b.rectangle()
        if r.top < 200 and r.left >= br.left - 60 and r.width() > 200:
            names.append(b.element_info.name or "")
    return names


def opened_chat(win, expected):
    """Chat sach mein khuli? (1) right side message box dikhe aur uska naam match ho, AUR
    (2) upar header mein bhi wahi naam ho. Dono milein tabhi (title, box), warna (None, None)."""
    title, box = current_chat(win)
    if not title or not same_chat(title, expected):
        return None, None
    want = _norm(expected)
    if not any(want in _norm(h) for h in _header_names(win, box)):
        return None, None
    return title, box


def _wait_open(win, expected, timeout=CHAT_OPEN_WAIT + 1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.25)
        title, box = opened_chat(win, expected)
        if title:
            return title, box
    return None, None


def _press_enter_on(row, how):
    """Keyboard se row kholo. Enter SIRF tab jab focus pakka isi row (ya uske andar) pe ho -
    message box pe kabhi Enter nahi (usme draft ho to chala jaata).
    how="down": search box se Down arrow jab tak row pe na pahunche | "focus": row pe seedha focus."""
    from pywinauto.keyboard import send_keys
    targets = [row] + row.descendants()
    if how == "focus":
        try:
            row.set_focus()
        except Exception:
            pass
        time.sleep(0.15)
    else:
        for _ in range(8):
            if _has_focus(*targets):
                break
            send_keys("{DOWN}")
            time.sleep(0.15)
    if not _has_focus(*targets):
        return False
    send_keys("{ENTER}")
    return True


def open_result(win, row, expected, methods=("keyboard", "click"), how="down"):
    """Chat kholo: har tareeka ek baar, total MAX_OPEN_TRIES (2) - kabhi bina limit ke retry
    ya dobara search nahi. Return (title, box, method) ya (None, None, None)."""
    for attempt, method in enumerate(methods[:MAX_OPEN_TRIES], 1):
        t = time.time()
        if method == "keyboard":
            pressed = _press_enter_on(row, how)
        else:
            (_title_item(row) or row).click_input()
            pressed = True
        title, box = _wait_open(win, expected) if pressed else (None, None)
        log(f"chat khuli? #{attempt} {method}", t, bool(title),
            "" if pressed else "(focus row pe nahi aaya, Enter nahi dabaya)")
        if title:
            return title, box, method
    return None, None, None


def open_self(win, methods=("keyboard", "click")):
    """Apni "(You)" chat: search NAHI ("You" se "Yash" jaise naam bhi aate) - Chat list mein
    sabse upar pinned hoti hai, wahin se kholo. Return (title, box, method) ya (None, None, None)."""
    t = time.time()
    doc = _doc(win)
    grid = next((g for g in doc.descendants(control_type="DataGrid")
                 if (g.element_info.name or "").strip() == CHAT_LIST), None)
    row = None
    for r in (grid.children()[:5] if grid else []):
        if any("(You)" in (d.element_info.name or "") for d in [r] + r.descendants(control_type="DataItem")):
            row = r
            break
    log("(You) chat list mein", t, row is not None)
    if row is None:
        return None, None, None
    return open_result(win, row, _result_title(row), methods, how="focus")


# ---------------- Send ----------------
def _count_in_chat(win, snippet):
    """Chat mein kitne elements ke naam mein ye text hai (bhejne se pehle/baad compare)."""
    doc = _doc(win)
    n = 0
    for e in doc.descendants():
        if snippet in (e.element_info.name or ""):
            n += 1
    return n


def send_in_open_chat(win, box, message):
    """Khuli chat ke message box mein paste + Enter; phir check ki message chat mein dikha."""
    from pywinauto.keyboard import send_keys
    snippet = message.strip()[:25]
    before = _count_in_chat(win, snippet)
    box.click_input()
    time.sleep(0.15)
    if not _has_focus(box):              # Focus message box pe nahi -> kuch type nahi
        return False
    send_keys("^a{BACKSPACE}")           # Pehle se pada draft saaf - warna message ke saath chala jaata
    _paste(message)
    send_keys("{ENTER}")
    for _ in range(10):                  # 5 second tak dekho
        time.sleep(0.5)
        if _count_in_chat(win, snippet) > before:
            return True
    return False


# ---------------- Calls ----------------
def _header_button(win, pattern, timeout=5):
    """Chat header (upar) mein naam se button dhoondho."""
    deadline = time.time() + timeout
    doc = _doc(win)
    while time.time() < deadline:
        for b in doc.descendants(control_type="Button"):
            if pattern.search((b.element_info.name or "").strip()):
                return b
        time.sleep(0.5)
    return None


def press_call(win, video=False):
    """Voice/Video call button dabao (naye WhatsApp mein pehle 'Call' menu ho sakta hai)."""
    target = VIDEO_CALL if video else VOICE_CALL
    btn = _header_button(win, target, timeout=3)
    if btn is None:
        menu = _header_button(win, CALL_MENU, timeout=2)
        if menu is not None:
            menu.click_input()
            time.sleep(0.8)
            doc = _doc(win)
            for e in doc.descendants():
                if e.element_info.control_type in ("Button", "MenuItem") and target.search(e.element_info.name or ""):
                    btn = e
                    break
    if btn is None:
        raise RuntimeError(("Video" if video else "Voice") + " call button nahi mila")
    btn.click_input()


def end_call():
    """Chal rahi WhatsApp call kaato: kisi bhi WhatsApp window mein 'End call' button."""
    from pywinauto import Desktop
    for w in Desktop(backend="uia").windows():
        try:
            if "whatsapp" not in (w.window_text() or "").lower():
                continue
            for b in w.descendants(control_type="Button"):
                if END_CALL.search((b.element_info.name or "").strip()):
                    b.click_input()
                    return True
        except Exception:
            continue
    return False
