# ============================================
# ui.py - JARVIS ki screen
#   Terminal mein print HAMESHA hota hai. Agar 3D window (ui/index.html,
#   pywebview) khuli hai to wahi baat window.jarvis ke functions ko bhi jaati hai:
#     set_state -> jarvis.setState(...) / jarvis.sleep()
#     log       -> jarvis.log(...)
#     wake      -> jarvis.wake()
#     add_message -> jarvis.addMessage('user'/'ai', text)
#     set_stats -> jarvis.setStats(cpu, ram, battery)
#     set_level -> jarvis.setLevel(0..1)   (bolte waqt orb naache)
# ============================================

import json         # Python ki value ko JavaScript mein bhejne layak text banana
import threading    # Window mein ek waqt pe ek hi JS call (thread-safe)
import time         # setLevel ko zyada tez na bhejna

# JARVIS abhi kis haal mein hai: "sleeping", "listening", "thinking", "speaking", "standby"
current_state = "sleeping"

# pywebview ki window - main.py set karta hai. None = sirf terminal (window nahi)
window = None
_js_lock = threading.Lock()
_last_level_sent = 0.0


def _js(func, *args):
    """window.jarvis.func(args...) chalao. Window na ho ya band ho gayi ho to chupchap chhod do.
    (JSON se bhejte hain taaki text mein quote/newline/Hindi se JS na toote)"""
    if window is None:
        return
    arg_text = ", ".join(json.dumps(a, ensure_ascii=False) for a in args)
    code = f"window.jarvis && window.jarvis.{func} && window.jarvis.{func}({arg_text})"
    try:
        with _js_lock:
            window.evaluate_js(code)
    except Exception:
        pass       # Window band ho rahi ho to error se JARVIS na ruke


def set_state(state):
    """JARVIS ki halat badlo (terminal + UI animation)."""
    global current_state
    if state != current_state:
        current_state = state
        print(f"  [{state}]")
        if state == "sleeping":
            _js("sleep")                 # UI apni sleep animation chalata hai
        else:
            _js("setState", state)       # 'listening' / 'thinking' / 'speaking' / 'standby'


def log(message):
    """Chhota status message, jaise 'Opening Chrome...' (terminal + UI log)."""
    print(f"  > {message}")
    _js("log", message)


def wake(text=None):
    """Wake word suna - UI mein shockwave/animation. text diya to UI wahi line chat mein
    dikhata hai (warna HTML apni "Good evening, Krish..." wali line daalta hai)."""
    if text:
        _js("wake", text)
    else:
        _js("wake")


def add_message(role, text):
    """Chat mein message dikhao. role = 'user' (Krish) ya 'ai' (JARVIS)."""
    _js("addMessage", role, text)


def set_stats(cpu, ram, battery):
    """CPU %, RAM %, battery % (desktop pe battery None)."""
    _js("setStats", cpu, ram, battery)


def set_level(level):
    """Bolte waqt awaaz ki taakat 0..1 - orb isse naachta hai. (Max ~25 baar/second)"""
    global _last_level_sent
    now = time.time()
    if level > 0 and now - _last_level_sent < 0.04:
        return
    _last_level_sent = now
    _js("setLevel", round(max(0.0, min(1.0, float(level))), 3))
