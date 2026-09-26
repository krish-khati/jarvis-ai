# ============================================
# whatsapp.py - WhatsApp Desktop aur Phone Link ko "insaan ki tarah" chalana
#   - Message: whatsapp://send?phone=..&text=.. link se chat khulti hai, phir Enter
#   - Call: chat kholke "Voice call"/"Video call" button dhoondh ke dabate hain (pywinauto)
#   - Phone call: tel: link -> Windows Phone Link app
# Koi unofficial WhatsApp library nahi (ban ka risk nahi) - sirf official app ka UI.
# NOTE: Ye functions tools.py se tabhi bulaye jaate hain jab confirm ho chuka ho
#       aur DRY_RUN band ho.
# ============================================

import os
import re
import time
from urllib.parse import quote

import contacts

CHAT_LOAD_SECONDS = 4      # Chat khulne ke baad Enter se pehle itna ruko (slow PC pe badhao)
WINDOW_TIMEOUT = 20        # WhatsApp window aane ka max intezaar

VOICE_CALL = re.compile(r"(?i)^(voice call|audio call|voice)$")
VIDEO_CALL = re.compile(r"(?i)^(video call|video)$")
CALL_MENU = re.compile(r"(?i)^(call|calls|start call)$")
END_CALL = re.compile(r"(?i)(end call|hang ?up|leave call|end)")


def _whatsapp_window():
    """WhatsApp Desktop ki main window dhoondho (aane tak ruko)."""
    from pywinauto import Desktop
    deadline = time.time() + WINDOW_TIMEOUT
    while time.time() < deadline:
        for w in Desktop(backend="uia").windows():
            try:
                if re.match(r"(?i)^whatsapp", w.window_text()):
                    return w
            except Exception:
                continue
        time.sleep(0.5)
    raise RuntimeError("WhatsApp Desktop ki window nahi mili (app install/login hai?)")


def _open_chat(number, text=None):
    """whatsapp://send link se us number ki chat kholo (text diya to box mein bhar jaata hai)."""
    url = f"whatsapp://send?phone={contacts.digits(number)}"
    if text:
        url += "&text=" + quote(text)
    os.startfile(url)                 # Windows WhatsApp Desktop ko link deta hai
    win = _whatsapp_window()
    time.sleep(CHAT_LOAD_SECONDS)      # Chat aur message box load hone do
    win.set_focus()
    return win


def send_message(number, message):
    """Chat kholo (message box mein bhar ke) aur Enter dabao."""
    from pywinauto.keyboard import send_keys
    _open_chat(number, message)
    send_keys("{ENTER}")
    time.sleep(0.8)
    return f"WhatsApp message sent to {contacts.mask(number)}"


def _find_button(win, pattern, timeout=8):
    """Window mein naam se button dhoondho (chat load hone tak baar-baar koshish)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            for b in win.descendants(control_type="Button"):
                name = (b.window_text() or "").strip()
                if name and pattern.search(name):
                    return b
        except Exception:
            pass
        time.sleep(0.5)
    return None


def call(number, video=False):
    """Chat kholke Voice/Video call button dabao."""
    win = _open_chat(number)
    target = VIDEO_CALL if video else VOICE_CALL
    btn = _find_button(win, target)
    if btn is None:
        # Naye WhatsApp mein pehle "Call" button, phir menu mein Voice/Video
        menu = _find_button(win, CALL_MENU, timeout=3)
        if menu is not None:
            menu.click_input()
            time.sleep(0.8)
            from pywinauto import Desktop
            for w in Desktop(backend="uia").windows():
                btn = _find_button(w, target, timeout=1) if re.match(r"(?i)whatsapp", w.window_text() or "") else None
                if btn:
                    break
    if btn is None:
        raise RuntimeError(("Video" if video else "Voice") + " call button nahi mila (WhatsApp ka design badla ho sakta hai)")
    btn.click_input()
    return f"WhatsApp {'video' if video else 'voice'} call started to {contacts.mask(number)}"


def end_call():
    """Chal rahi WhatsApp call kaato: kisi bhi WhatsApp window mein 'End call' button dabao."""
    from pywinauto import Desktop
    for w in Desktop(backend="uia").windows():
        try:
            if not re.search(r"(?i)whatsapp", w.window_text() or ""):
                continue
        except Exception:
            continue
        btn = _find_button(w, END_CALL, timeout=1)
        if btn is not None:
            btn.click_input()
            return "Call ended"
    raise RuntimeError("Koi chalti WhatsApp call nahi mili")


def phone_call(number):
    """Normal phone call: tel: link Windows Phone Link app ko jaata hai (phone Bluetooth se juda ho)."""
    d = contacts.digits(number)
    os.startfile(f"tel:+{d}" if str(number).strip().startswith("+") else f"tel:{d}")
    return f"Phone Link call started to {contacts.mask(number)} (Phone Link mein 'Call' dabana pad sakta hai)"
