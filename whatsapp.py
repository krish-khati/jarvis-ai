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
def _window():
    """WhatsApp kholo (band/tray mein ho to bhi) aur main window ka spec do.
    Title "(10) WhatsApp" jaisa hota hai - unread ginti aage lagti hai."""
    from pywinauto import Desktop
    os.startfile(APP_ID)
    deadline = time.time() + 20
    while time.time() < deadline:
        for w in Desktop(backend="uia").windows():
            try:
                if w.class_name() == "WinUIDesktopWin32WindowClass" and re.search(r"(?i)\bwhatsapp$", w.window_text() or ""):
                    if w.is_minimized():
                        w.restore()
                    w.set_focus()
                    return Desktop(backend="uia").window(handle=w.handle)
            except Exception:
                continue
        time.sleep(0.5)
    raise RuntimeError("WhatsApp Desktop ki window nahi khuli (install/login hai?)")


def _doc(win):
    return win.child_window(auto_id="RootWebArea", control_type="Document", found_index=0)


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
    """Search box saaf karo (purana naam na pada rahe)."""
    from pywinauto.keyboard import send_keys
    try:
        box = _search_box(win, timeout=3)
        box.click_input()
        send_keys("^a{BACKSPACE}{ESC}")
    except Exception:
        pass


def _search_box(win, timeout=10):
    """Search box dhoondho. Dhyan: box mein text ho to uska naam khaali ho jaata hai
    (naam sirf placeholder "Search or start a new chat" hai) - isliye naam pe bharosa nahi,
    jagah se pehchante hain: jo Edit "Type a message..." nahi hai aur sabse upar hai."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            doc = _doc(win).wrapper_object()
            edits = [e for e in doc.descendants(control_type="Edit")
                     if not MESSAGE_BOX.match(e.element_info.name or "")]
            if edits:
                return min(edits, key=lambda e: e.rectangle().top)
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("WhatsApp ka search box nahi mila")


def search(query):
    """Search box mein naam likho; chat results ki list do: [(title, row_wrapper), ...]"""
    from pywinauto.keyboard import send_keys
    win = _window()
    doc = _doc(win)
    box = _search_box(win, timeout=15)
    box.click_input()
    send_keys("^a{BACKSPACE}")          # Purana text saaf
    _paste(query)

    # Results tabhi padho jab (1) search box mein SAHI naam ho aur (2) list do baar
    # lagatar same aaye - warna pichle search ke purane results padh lete (galat chat khulti)
    deadline = time.time() + RESULTS_WAIT + 6
    last = None
    while time.time() < deadline:
        time.sleep(0.6)
        try:
            typed = (box.get_value() or "").strip()
        except Exception:
            typed = ""
        if typed != query.strip():
            continue
        results = _read_results(doc)
        titles = [t for t, _ in results]
        if last is not None and titles == last:
            return win, results
        last = titles
    return win, []                       # Pakka nahi ho paya -> kuch mat kholo


def _read_results(doc):
    """Results grid se chat/contact rows padho ("Messages" section wale chhod ke)."""
    try:
        grid = doc.child_window(title=RESULTS_GRID, control_type="DataGrid", found_index=0).wrapper_object()
    except Exception:
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


def open_result(win, row):
    """Result ke naam wale hisse pe click karke chat kholo; header se asli chat ka naam padho.
    Chat khulne ka 4 second tak intezaar (baar-baar check). Na khule to (None, None)."""
    (_title_item(row) or row).click_input()
    deadline = time.time() + CHAT_OPEN_WAIT + 2
    while time.time() < deadline:
        time.sleep(0.5)
        title, box = current_chat(win)
        if title:
            return title, box
    return None, None


def current_chat(win):
    """Khuli chat ka naam - message box "Type a message to <naam>" se (header wala hi naam)."""
    doc = _doc(win).wrapper_object()
    for e in doc.descendants(control_type="Edit"):
        m = MESSAGE_BOX.match(e.element_info.name or "")
        if m:
            return m["name"].strip(), e
    return None, None


# ---------------- Send ----------------
def _count_in_chat(win, snippet):
    """Chat mein kitne elements ke naam mein ye text hai (bhejne se pehle/baad compare)."""
    doc = _doc(win).wrapper_object()
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
    doc = _doc(win).wrapper_object()
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
            doc = _doc(win).wrapper_object()
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
