# ============================================
# ui.py - JARVIS ki screen
#   Terminal mein print HAMESHA hota hai. Agar 3D window (ui/index.html,
#   pywebview) khuli hai to wahi baat window.jarvis ke functions ko bhi jaati hai:
#     set_state -> jarvis.setState(...) / jarvis.sleep()
#     log       -> jarvis.log(...)
#     wake      -> window saamne + jarvis.wake()
#     add_message -> jarvis.addMessage('user'/'ai', text)
#     set_stats -> jarvis.setStats(cpu, ram, battery, disk, net_MBps)
#     set_weather -> jarvis.setWeather(city, temp, desc)
#     action    -> jarvis.action(id, title, detail, 'running'/'done'/'failed')
#     set_level -> jarvis.setLevel(0..1)   (bolte waqt waveform naache)
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


def wake():
    """Wake word suna - window saamne lao, phir UI mein flash + panels slide-in."""
    show_window()
    _js("wake")


def show_window():
    """Chhupi window ko saamne lao (fullscreen)."""
    if window is None:
        return
    try:
        window.show()
        window.restore()          # Minimize ho to wapas
    except Exception:
        pass


def hide_window():
    """Window chhupao - JARVIS background (tray) mein chalta rehta hai."""
    if window is None:
        return
    try:
        window.hide()
    except Exception:
        pass


def add_message(role, text):
    """Chat mein message dikhao. role = 'user' (Krish) ya 'ai' (JARVIS)."""
    _js("addMessage", role, text)


def set_stats(cpu, ram, battery, disk=None, net_mbps=None):
    """CPU %, RAM %, battery % (desktop pe None), disk %, network MB/s."""
    _js("setStats", cpu, ram, battery, disk, net_mbps)


def set_weather(city, temp, desc):
    """Weather panel: shahar, temperature (°C), description."""
    _js("setWeather", city, temp, desc)


def action(action_id, title, detail, status):
    """Activity panel mein kaam dikhao/update karo. status = 'running' / 'done' / 'failed'."""
    _js("action", action_id, title, detail, status)


def set_level(level):
    """Bolte waqt awaaz ki taakat 0..1 - orb isse naachta hai. (Max ~25 baar/second)"""
    global _last_level_sent
    now = time.time()
    if level > 0 and now - _last_level_sent < 0.04:
        return
    _last_level_sent = now
    _js("setLevel", round(max(0.0, min(1.0, float(level))), 3))
