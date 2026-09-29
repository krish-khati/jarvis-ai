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
#   Window chhupi ho to: JS ki animations/canvas band (jarvis.setVisible), stats/level
#   bhejna band, aur WebView2 ki memory kam (Low target + TrySuspend).
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
_visible = False        # Window abhi dikh rahi hai? (shuru mein hidden=True)
_suspended = False      # WebView2 TrySuspend ho chuka hai?
_last_stats = None      # Chhupi window mein aaye stats - dikhne pe ek baar bhej dete hain
_pending = []           # Suspend ke dauran aaye zaroori JS calls (message/action) - resume pe chalte hain
_MAX_PENDING = 60
_pending_state = None   # Suspend ke dauran aayi aakhri state call ("sleep"/"setState")


def _js(func, *args):
    """window.jarvis.func(args...) chalao. Window na ho ya band ho gayi ho to chupchap chhod do.
    (JSON se bhejte hain taaki text mein quote/newline/Hindi se JS na toote)"""
    global _pending_state
    if window is None:
        return
    arg_text = ", ".join(json.dumps(a, ensure_ascii=False) for a in args)
    code = f"window.jarvis && window.jarvis.{func} && window.jarvis.{func}({arg_text})"
    with _js_lock:
        if _suspended:
            # Page suspend hai - evaluate_js atak jaata. Zaroori cheezein yaad rakho, dikhne pe chalengi
            if func in ("sleep", "setState"):
                _pending_state = (func, args)
            elif func in ("addMessage", "action", "log", "setWeather") and len(_pending) < _MAX_PENDING:
                _pending.append((func, args))
            return
        try:
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


def _webview2(fn):
    """fn(CoreWebView2) ko window ke UI thread pe chalao. Kuch na mile/fail ho to None."""
    try:
        from System import Func, Type
        from webview.platforms.winforms import BrowserView
        form = BrowserView.instances.get(window.uid)
        box = []

        def _run():
            try:
                box.append(fn(form.browser.webview.CoreWebView2))   # CoreWebView2 sirf UI thread pe milta hai
            except Exception:
                pass
        form.Invoke(Func[Type](_run))
        return box[0] if box else None
    except Exception:
        return None


def _memory_level(low):
    """WebView2 ko batao ki memory kam rakho (Low) ya normal (Normal)."""
    def _set(core):
        from Microsoft.Web.WebView2.Core import CoreWebView2MemoryUsageTargetLevel as L
        core.MemoryUsageTargetLevel = L.Low if low else L.Normal
    _webview2(_set)


def _suspend():
    """Chhupi page ko suspend karo - CPU/GPU ~0 aur memory kam."""
    global _suspended
    if _webview2(lambda core: core.TrySuspendAsync()) is not None:   # Task milta hai; browser khud suspend karta hai
        _suspended = True


def _resume():
    """Suspend khatam - JS calls se pehle zaroori."""
    global _suspended
    if _suspended:
        _webview2(lambda core: core.Resume())
        _suspended = False


def is_visible():
    """Window abhi dikh rahi hai? (stats jaise kaam chhupi window mein band rakhne ke liye)"""
    return _visible


def show_window():
    """Chhupi window ko saamne lao (fullscreen)."""
    global _visible, _pending_state
    if window is None:
        return
    try:
        with _js_lock:
            _resume()
            _memory_level(False)
        window.show()
        window.restore()          # Minimize ho to wapas
    except Exception:
        pass
    _visible = True
    if _pending_state:
        f, a = _pending_state
        _pending_state = None
        _js(f, *a)
    _js("setVisible", True)       # Animations wapas (awake ho tabhi chalti hain)
    while _pending:
        f, a = _pending.pop(0)
        _js(f, *a)
    if _last_stats:
        _js("setStats", *_last_stats)


def hide_window():
    """Window chhupao - JARVIS background (tray) mein chalta rehta hai."""
    global _visible
    if window is None:
        return
    _visible = False
    _js("setVisible", False)      # Pehle JS ki animation/canvas roko, phir window chhupao
    try:
        window.hide()
    except Exception:
        pass
    time.sleep(0.15)              # WebView2 ko "hidden" hone do (TrySuspend ke liye zaroori)
    with _js_lock:                # Koi JS call beech mein na chale
        if not _visible:          # Is beech kisi ne window wapas dikha di ho to suspend mat karo
            _memory_level(True)
            _suspend()


def add_message(role, text):
    """Chat mein message dikhao. role = 'user' (Krish) ya 'ai' (JARVIS)."""
    _js("addMessage", role, text)


def set_stats(cpu, ram, battery, disk=None, net_mbps=None):
    """CPU %, RAM %, battery % (desktop pe None), disk %, network MB/s.
    Window chhupi ho to bhejna band (bas yaad rakho, dikhne pe ek baar bhejte hain)."""
    global _last_stats
    _last_stats = (cpu, ram, battery, disk, net_mbps)
    if not _visible:
        return
    _js("setStats", *_last_stats)


def set_weather(city, temp, desc):
    """Weather panel: shahar, temperature (°C), description."""
    _js("setWeather", city, temp, desc)


def action(action_id, title, detail, status):
    """Activity panel mein kaam dikhao/update karo. status = 'running' / 'done' / 'failed'."""
    _js("action", action_id, title, detail, status)


def set_level(level):
    """Bolte waqt awaaz ki taakat 0..1 - orb isse naachta hai. (Max ~25 baar/second)"""
    global _last_level_sent
    if not _visible:
        return
    now = time.time()
    if level > 0 and now - _last_level_sent < 0.04:
        return
    _last_level_sent = now
    _js("setLevel", round(max(0.0, min(1.0, float(level))), 3))
