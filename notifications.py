# ============================================
# notifications.py - WhatsApp ke aaye hue messages (Windows notifications se)
#   - Windows ka UserNotificationListener (pywinrt) har 3 second padhte hain
#   - Sirf WhatsApp ki notifications; sab kuch SIRF memory (RAM) mein -
#     koi file, koi log nahi. JARVIS band = sab mit gaya.
#   - Ye sirf PADHTA hai. Reply kabhi apne aap nahi hota - hamesha Krish se
#     poochh ke, confirm karke (tools.send_whatsapp).
# Pehli baar: Settings > Privacy & security > Notifications >
#   "Let apps access your notifications" ON hona chahiye.
# ============================================

import asyncio
import threading
import time

POLL_SECONDS = 3
MAX_KEEP = 50

_lock = threading.Lock()
_items = []          # [{"id", "sender", "text", "time", "announced", "read"}]
_seen = set()        # Jo notification id dekh chuke
_status = "not started"
last_sender = None   # Aakhri message kisne bheja (reply ke liye)
last_text = None
awaiting_reply = False   # JARVIS ne "Reply karun?" poocha hai - agla "haan/nahi" isi ke liye


def _parse(n):
    """Notification se (sender, text) nikaalo. WhatsApp nahi hai to None."""
    try:
        app = n.app_info.display_info.display_name
    except Exception:
        return None
    if "whatsapp" not in (app or "").lower():
        return None
    from winrt.windows.ui.notifications import KnownNotificationBindings
    binding = n.notification.visual.get_binding(KnownNotificationBindings.toast_generic)
    if binding is None:
        return None
    texts = [e.text for e in binding.get_text_elements() if e.text]
    if not texts:
        return None
    sender = texts[0].strip()
    text = " ".join(t.strip() for t in texts[1:]) or "(message)"
    return sender, text


async def _read_all():
    from winrt.windows.ui.notifications.management import UserNotificationListener
    from winrt.windows.ui.notifications import NotificationKinds
    return await UserNotificationListener.current.get_notifications_async(NotificationKinds.TOAST)


def _poll(first=False):
    """Nayi WhatsApp notifications list mein jodo. first=True: purani announce mat karo."""
    global last_sender, last_text
    for n in asyncio.run(_read_all()):
        if n.id in _seen:
            continue
        _seen.add(n.id)
        parsed = _parse(n)
        if not parsed:
            continue
        sender, text = parsed
        with _lock:
            _items.append({"id": n.id, "sender": sender, "text": text, "time": time.time(),
                           "announced": first, "read": False})
            del _items[:-MAX_KEEP]
            last_sender, last_text = sender, text


def _loop():
    global _status
    first = True
    while True:
        try:
            _poll(first)
            _status = "running"
        except Exception as e:
            _status = f"error: {type(e).__name__}"
        first = False
        time.sleep(POLL_SECONDS)


def access_ok():
    """Windows ne notifications padhne ki ijazat di hai? (koi popup nahi kholta)"""
    try:
        from winrt.windows.ui.notifications.management import UserNotificationListener
        return int(UserNotificationListener.current.get_access_status()) == 1   # 1 = Allowed
    except Exception:
        return False


def start():
    """Background mein notifications padhna shuru karo. Ijazat na ho to setup batao."""
    global _status
    if not access_ok():
        _status = "no access"
        print("  [WhatsApp notifications] Windows permission nahi hai. Settings > Privacy & security >"
              " Notifications > 'Let apps access your notifications' ON karo, phir JARVIS restart karo.")
        return False
    threading.Thread(target=_loop, daemon=True, name="notifications").start()
    return True


def status():
    return _status


def take_new():
    """Jo messages abhi tak announce nahi hue - lo aur 'announced' mark karo."""
    with _lock:
        new = [dict(i) for i in _items if not i["announced"]]
        for i in _items:
            i["announced"] = True
    return new


def count_new():
    with _lock:
        return sum(1 for i in _items if not i["announced"])


def unread(n=5):
    """Aakhri n bina padhe messages (purane se naya) - aur unhe 'read' mark karo."""
    with _lock:
        items = [i for i in _items if not i["read"]][-n:]
        for i in items:
            i["read"] = True
            i["announced"] = True
        return [dict(i) for i in items]


def mark_read(sender):
    with _lock:
        for i in _items:
            if i["sender"] == sender:
                i["read"] = True


def add_fake(sender, text):
    """Sirf TEST ke liye: nakli notification daalo (DRY_RUN tests)."""
    global last_sender, last_text
    with _lock:
        _items.append({"id": f"fake-{time.time()}", "sender": sender, "text": text,
                       "time": time.time(), "announced": False, "read": False})
        last_sender, last_text = sender, text
