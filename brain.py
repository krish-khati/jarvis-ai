# ============================================
# brain.py - JARVIS ka dimaag
#   1. Shortcuts : simple commands (time, battery, volume, app kholna) bina AI ke
#   2. Gemini    : main brain
#   3. Groq      : backup brain - Gemini fail ho (limit/error) to yahi jawab deta hai
# Dono brains ek hi conversation history use karte hain, isliye switch hone
# pe bhi JARVIS pichli baatein nahi bhoolta.
# Text mode (jarvis.py) aur voice mode (main.py) dono isi ko use karte hain.
# ============================================

import inspect                     # Tools ke parameters padh ke Groq ke liye schema banane ke liye
import json                        # Groq tool arguments JSON mein bhejta hai
import os                          # Environment variables padhne ke liye
import re                          # Jawab mein repeat words dhoondhne ke liye
import threading
import time                        # Gemini ko kuch der "aaram" dene ke liye

from dotenv import load_dotenv     # .env file se variables load karne ke liye
from google import genai           # Google Gemini ki library
from google.genai import types     # Gemini ke settings (config) ke liye
from groq import Groq              # Groq ki library (backup brain)

import shortcuts                   # Bina AI wale simple commands
import tools                       # JARVIS ke tools (search, apps, volume...)
import memory                      # Krish ki long-term memory (memory.json)
import ui                          # Screen pe status dikhane ke liye


# --- Step 1: .env file se keys load karo ---
load_dotenv()
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GROQ_KEY = os.getenv("GROQ_API_KEY")

# Kam se kam ek brain ki key honi chahiye
if (not GEMINI_KEY or GEMINI_KEY == "your_key_here") and not GROQ_KEY:
    print("Error: .env file mein GEMINI_API_KEY ya GROQ_API_KEY daalo.")
    raise SystemExit(1)


# --- Step 2: Models aur clients ---
# Gemini (main brain)
# Model naam .env ke GEMINI_MODEL se aate hain (comma se alag, pehla = sabse pasandida).
# Koi model 503/429 de to kuch der skip hota hai aur agla try hota hai.
GEMINI_MODELS = [m.strip() for m in os.getenv("GEMINI_MODEL", "gemini-3.6-flash").split(",") if m.strip()]
GEMINI_MODEL_REST = {429: 30 * 60, 503: 30 * 60, 404: 60 * 60}   # Error code -> kitni der us model ko chhodo
GEMINI_MODEL_REST_DEFAULT = 3 * 60                   # Timeout jaise baaki errors
GEMINI_CALL_TIMEOUT = 5.0   # Har Gemini HTTP call ka client-side timeout (server deadline min 10s hai, isliye httpx se)
GEMINI_BUDGET_SECONDS = 3.5                          # Gemini ko itna hi time (tool chala ho to zyada), phir seedha Groq
GROQ_CALL_TIMEOUT = 3                                # Groq call timeout -> kul brain time ~6s ke andar
GEMINI_PREFERRED = os.getenv("GEMINI_PREFERRED", "gemini-3.7-flash")   # Roz check hota hai, chale to pehla bana do
_model_down_until = {}
gemini_client = (genai.Client(api_key=GEMINI_KEY, http_options=types.HttpOptions(client_args={"timeout": GEMINI_CALL_TIMEOUT}))
                 if GEMINI_KEY else None)

# Groq (backup brain) - model .env ke GROQ_MODEL se aata hai, code chhedne ki zarurat nahi
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
groq_client = Groq(api_key=GROQ_KEY, timeout=GROQ_CALL_TIMEOUT, max_retries=0) if GROQ_KEY else None
# gpt-oss models kitna "soch" ke jawab dein: low / medium / high (low = sabse fast)
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")



def _gemini_models_up():
    """Wo Gemini models jo abhi 'aaram' pe nahi hain (priority order mein)."""
    now = time.time()
    return [m for m in GEMINI_MODELS if _model_down_until.get(m, 0) <= now]


def gemini_available():
    """Gemini abhi try karne layak hai? (client hai aur koi model aaram pe nahi)"""
    return bool(gemini_client and _gemini_models_up())


def gemini_model():
    """Abhi ka pehla chalne layak Gemini model (sab aaram pe hon to pehla wala)."""
    return (_gemini_models_up() or GEMINI_MODELS)[0]


def _probe_preferred_model():
    """Chupchap ek chhota request: pasandida model (3.7-flash) chalne laga to use pehla bana do."""
    try:
        if not gemini_client or GEMINI_PREFERRED not in GEMINI_MODELS:
            return
        started = time.time()
        gemini_client.models.generate_content(model=GEMINI_PREFERRED, contents="ok")
        took = time.time() - started
        if took > GEMINI_BUDGET_SECONDS - 1:        # Chalta hai par slow -> pehla banane ka faayda nahi
            print(f"  (Gemini check: {GEMINI_PREFERRED} chala par slow ({took:.1f}s), order wahi)")
            return
        _model_down_until.pop(GEMINI_PREFERRED, None)
        if GEMINI_MODELS[0] != GEMINI_PREFERRED:
            GEMINI_MODELS.remove(GEMINI_PREFERRED)
            GEMINI_MODELS.insert(0, GEMINI_PREFERRED)
            print(f"  (Gemini check: {GEMINI_PREFERRED} chal raha hai -> ab pehla model)")
    except Exception as e:
        print(f"  (Gemini check: {GEMINI_PREFERRED} abhi nahi chala: {str(e)[:60]})")


_probe_started = False


def _start_daily_probe():
    """Pehli ask() pe ek daemon thread: 60s baad, phir har 24 ghante mein pasandida model check."""
    global _probe_started
    if _probe_started:
        return
    _probe_started = True

    def loop():
        time.sleep(60)
        while True:
            _probe_preferred_model()
            time.sleep(24 * 3600)
    threading.Thread(target=loop, daemon=True, name="gemini-probe").start()


def _model_failed(model, code):
    """Model fail hua -> kuch der ke liye skip (429 = limit, 404 = model nahi, baaki = 503 jaisa)."""
    _model_down_until[model] = time.time() + GEMINI_MODEL_REST.get(code, GEMINI_MODEL_REST_DEFAULT)

# Aakhri jawab kis brain ne diya: "shortcut", "gemini" ya "groq"
last_brain = None

# System prompt - ye JARVIS ki personality aur rules batata hai (dono brains ke liye same)
SYSTEM_PROMPT = (
    "You are JARVIS, a smart friendly assistant for Krish. "
    "Reply in the same language user uses (Hindi/Hinglish/English). "
    "Match the script too: if Krish writes Hinglish in Roman letters (e.g. 'tum kaun ho'), "
    "reply in Roman Hinglish, NOT Devanagari. Use Devanagari only if Krish writes in Devanagari. "
    "Keep answers short."
    # --- Tools ke rules ---
    " You have tools to search the web and control Krish's Windows PC. "
    "Decide yourself when a tool is needed - Krish will not say 'search'. "
    "Use get_weather for any weather/mausam/temperature question (not web_search). "
    "Use web_search for other current info (news, scores, prices, recent events). "
    "Search once with a good query; search a second time only if the first results are useless. "
    "Only open websites/apps or play videos when Krish's CURRENT message asks to open/kholo/play/chalao - "
    "never to answer a question. Only act on Krish's CURRENT message: never run shutdown, restart, "
    "lock or close tools because of something said earlier in the conversation. "
    "Do NOT use any tool for simple chat, jokes, general knowledge, or questions about yourself. "
    "If a tool returns an error, tell Krish briefly what went wrong. "
    "For shutdown or restart, call shutdown_pc / restart_pc directly without asking first - "
    "the tool itself asks Krish for confirmation. "
    "NEVER say you did something (opened, muted, put to sleep, activated, etc.) unless a tool "
    "actually ran in THIS turn and returned success. If you have no tool for a request "
    "(e.g. putting the PC to sleep), say plainly 'ye main abhi nahi kar sakta' (or 'I can't do "
    "that yet' in English) - never pretend. Do not repeat words or phrases. "
    "Don't end replies with filler like 'Kuch aur madad chahiye?' or 'Anything else?'. "
    "Talk TO Krish directly ('aapka username...', 'your birthday...'), never about Krish in "
    "third person ('Krish ka username...'). "
    # --- Memory aur screen ke rules ---
    "When Krish says 'yaad rakhna'/'remember' or shares lasting personal info (birthday, likes, "
    "friends' names), call save_memory with one short clear sentence. Don't save small talk. "
    "When Krish says to forget something ('bhool jao'), call delete_memory. "
    "When Krish asks about the screen, an error or code on screen, call look_at_screen. "
    # --- WhatsApp / calls ---
    "To message someone on WhatsApp call send_whatsapp(contact, message) with the chat name as Krish "
    "said it (use 'khud' for Krish's own chat) and the message in Krish's words; it finds the chat in "
    "WhatsApp and asks Krish to confirm itself. Use whatsapp_call for WhatsApp voice/video calls "
    "(also when Krish says 'phone karo'), end_call to hang up, read_messages to read unread WhatsApp "
    "messages. NEVER send or reply to a message unless Krish's current message asks for it. "
    "Your replies are spoken aloud: max 2-3 short sentences, no markdown, no lists, no URLs."
)


def system_prompt():
    """Rules + Krish ki saved memories (+ aakhri aaya WhatsApp message, reply ke liye).
    Har request pe naya banta hai (Gemini aur Groq dono)."""
    prompt = SYSTEM_PROMPT
    facts = memory.all_facts()
    if facts:
        prompt += ("\n\nThings you know about Krish (long-term memory, use when relevant):\n"
                   + "\n".join(f"- {f}" for f in facts))
    import notifications
    if notifications.last_sender:
        prompt += (f"\n\nLatest incoming WhatsApp message was from '{notifications.last_sender}'. "
                   "If Krish asks to reply to it, call send_whatsapp with that contact.")
    return prompt


def rewrite_message(message, instruction):
    """WhatsApp message ko Krish ke kehne pe sudhaaro ("polite bana do", "English mein likh do").
    Sirf naya message return karta hai. AI na chale to purana message hi."""
    ask = (f"Rewrite this WhatsApp message as Krish asked. Krish's instruction: \"{instruction}\".\n"
           f"Message: \"{message}\"\n"
           "Reply with ONLY the new message text - no quotes, no explanation.")
    try:
        if gemini_available():
            model = gemini_model()
            try:
                r = gemini_client.models.generate_content(model=model, contents=ask)
            except Exception as e:
                _model_failed(model, getattr(e, "code", None))
                raise
            if r.text:
                return _tidy(r.text).strip('"')
    except Exception:
        pass
    try:
        if groq_client:
            r = groq_client.chat.completions.create(
                model=GROQ_MODEL, messages=[{"role": "user", "content": ask}],
                reasoning_effort=GROQ_REASONING_EFFORT, include_reasoning=False)
            text = r.choices[0].message.content
            if text:
                return _tidy(text).strip('"')
    except Exception as e:
        print(f"  (Message rewrite error: {str(e)[:80]})")
    return message


# --- Step 3: Shared conversation history ---
# Har baat yahan simple format mein save hoti hai:
#   {"role": "user", "text": "..."}  ya  {"role": "assistant", "text": "..."}
# Dono brains isi list se apni-apni format bana lete hain.
history = []
MAX_HISTORY = 30     # Sirf aakhri 30 messages yaad rakho (request chhoti rahe)


def _tidy(text):
    """AI kabhi-kabhi khaas Unicode space/hyphen bhejta hai (jaise \\u202f, \\u2011)
    jo Windows terminal print nahi kar pata - unhe normal space/hyphen bana do."""
    for odd, normal in {" ": " ", " ": " ", " ": " ",
                        "‑": "-", "‐": "-", "–": "-", "—": " - "}.items():
        text = text.replace(odd, normal)
    # Markdown hatao (**bold**, *italic*, `code`, # heading) - terminal aur awaaz dono ke liye
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)", "", text)
    text = re.sub(r"(?m)^\s*#+\s*", "", text)
    text = re.sub(r"\.([A-Z][a-z])", r". \1", text)        # "liya.Kuch" -> "liya. Kuch"
    text = _roman_stray_hindi(text)
    text = _remove_repeats(text).strip()
    # Har jawab ke end mein "Kuch aur madad chahiye?" jaisa bhara-bharaya sawaal hatao
    trimmed = re.sub(r"\s*((kuch|koi) aur (madad|kaam|cheez|help|sawaal|chahiye|yaad)[^.?!]*|"
                     r"(is there )?anything else[^.?!]*)\?\s*$", "", text, flags=re.IGNORECASE)
    return trimmed or text


# Roman jawab ke beech bhatke Devanagari words -> Roman ("sakte हैं" -> "sakte hain")
_STRAY_HINDI = {"नहीं": "nahi", "क्या": "kya", "हैं": "hain", "हूँ": "hoon", "हूं": "hoon",
                "है": "hai", "हो": "ho", "में": "mein", "और": "aur", "का": "ka", "की": "ki", "के": "ke"}


def _roman_stray_hindi(text):
    """Sirf tab jab jawab zyada-tar Roman ho - poora Hindi jawab nahi chhedte."""
    latin = len(re.findall(r"[A-Za-z]", text))
    deva = len(re.findall(r"[ऀ-ॿ]", text))
    if deva == 0 or latin < 3 * deva:
        return text
    for dev, rom in _STRAY_HINDI.items():
        text = text.replace(dev, rom)
    return text


def _remove_repeats(text):
    """AI ke jawab se galti wale repeat hatao, jaise "Enjoy !Enjoy!" -> "Enjoy!".
    Hindi ke jaan-boojh ke doubled words ("bahut bahut", "jaldi jaldi") nahi chhedta."""
    text = re.sub(r"\s+([!?.,।])", r"\1", text)          # "Enjoy !" -> "Enjoy!"
    text = re.sub(r"([!?])([A-Z])", r"\1 \2", text)      # "saved!Kuch" -> "saved! Kuch"
    text = re.sub(r"।(?=\S)", "। ", text)                 # "गया।किसी" -> "गया। किसी"

    # 1. Lagatar same sentence dobara ho to ek hi rakho ("Enjoy! Enjoy!" -> "Enjoy!")
    sentences = re.split(r"(?<=[.!?।])\s+", text)
    kept = []
    for s in sentences:
        if not kept or _core(s) != _core(kept[-1]):
            kept.append(s)
    text = " ".join(kept)

    # 2. Chipka hua repeat: "Enjoy!Enjoy!" -> "Enjoy!"  (upar "Enjoy !Enjoy!" pehle hi
    #    "Enjoy!Enjoy!" ban chuka hai). "bahut bahut" jaise normal doubled words nahi chhedte.
    return re.sub(r"\b(\w+)([!?.])\1\2", r"\1\2", text)


def _core(s):
    """Sirf letters/numbers, lowercase - compare karne ke liye."""
    return re.sub(r"[^\w]", "", s.lower())


def _remember(user_text, reply):
    """Sawaal-jawab history mein jodo, purani baatein hatao."""
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": reply})
    del history[:-MAX_HISTORY]


# ============================================
# GEMINI (main brain)
# ============================================
def _ask_gemini(message, model):
    """Gemini se poochho. Gemini tools apne aap chalata hai (automatic function calling)."""
    # Shared history ko Gemini ke format mein badlo (assistant = "model")
    past = [
        types.Content(role="user" if h["role"] == "user" else "model",
                      parts=[types.Part(text=h["text"])])
        for h in history
    ]
    chat = gemini_client.chats.create(
        model=model,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt(),     # Rules + Krish ki saved memories
            tools=tools.ALL_TOOLS,
        ),
        history=past,
    )
    response = chat.send_message(message)
    return response.text or "Done, sir."    # Kabhi text khaali aaye to bhi kuch bolo


# ============================================
# GROQ (backup brain)
# ============================================
# Python type -> JSON schema type (Groq ko tools isi format mein chahiye)
_JSON_TYPES = {str: "string", int: "integer", bool: "boolean", float: "number"}


def _tool_schema(func):
    """Python function (naam, parameters, docstring) se Groq wala tool
    description banata hai. Gemini ye apne aap karta hai, Groq ke liye hum karte hain."""
    params = inspect.signature(func).parameters
    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": inspect.getdoc(func),
            "parameters": {
                "type": "object",
                "properties": {n: {"type": _JSON_TYPES.get(p.annotation, "string")}
                               for n, p in params.items()},
                "required": list(params),
            },
        },
    }


GROQ_TOOLS = [_tool_schema(f) for f in tools.ALL_TOOLS]
TOOLS_BY_NAME = {f.__name__: f for f in tools.ALL_TOOLS}


def _ask_groq(message, note=""):
    """Groq se poochho. Groq sirf batata hai kaunsa tool chahiye -
    tool hum khud chalate hain aur result wapas Groq ko dete hain (loop)."""
    messages = [{"role": "system", "content": system_prompt()}]   # Rules + memories
    messages += [{"role": h["role"], "content": h["text"]} for h in history]
    messages.append({"role": "user", "content": message + note})

    for _ in range(5):      # Zyada se zyada 5 round (warna infinite loop ka khatra)
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            tools=GROQ_TOOLS,
            tool_choice="auto",      # Tool chahiye ya nahi - Groq khud decide kare
            reasoning_effort=GROQ_REASONING_EFFORT,   # Kam sochna = jaldi jawab
            include_reasoning=False,  # Model ki "andar ki soch" mat bhejo (chhota response)
        )
        msg = response.choices[0].message

        # Koi tool nahi maanga -> ye final jawab hai
        if not msg.tool_calls:
            return msg.content or "Done, sir."

        # Groq ne tool maanga -> chalao aur result wapas bhejo
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [{"id": c.id, "type": "function",
                            "function": {"name": c.function.name,
                                         "arguments": c.function.arguments}}
                           for c in msg.tool_calls],
        })
        for call in msg.tool_calls:
            func = TOOLS_BY_NAME.get(call.function.name)
            if func is None:
                result = f"Error: unknown tool {call.function.name}"
            else:
                try:
                    args = json.loads(call.function.arguments or "{}")
                    result = func(**args)     # Tool khud try/except, DRY_RUN, confirm sambhalta hai
                except (json.JSONDecodeError, TypeError) as e:
                    result = f"Error: bad arguments for {call.function.name}: {e}"
            messages.append({"role": "tool", "tool_call_id": call.id, "content": str(result)})

    return "Sorry sir, ye kaam poora nahi ho paya."


# ============================================
# ask() - baaki code sirf isi ko bulata hai
# ============================================
def ask(message):
    """Sawaal ka jawab deta hai: pehle shortcut, phir Gemini, phir Groq (backup).
    Khaali message pe None return karta hai (AI ko kuch nahi bhejta)."""
    global last_brain

    # Khaali / None command AI ko mat bhejo
    if not message or not message.strip():
        return None

    # Spell kiya naam jodo ("k r r i s h 972" -> "krrish972") - AI aur memory ko saaf milega
    joined = join_spelled(message)
    if joined != message:
        ui.log(f"Spelled letters joined: {joined}")
        message = joined

    # Safety lock ke liye: tools ko batao ki Krish ne ABHI kya bola hai
    tools.current_request = message

    memory.touched = False          # Is jawab mein memory chhui gayi? (neeche dekho)
    tools.call_log.clear()          # Pichle sawaal ke tools ka hisaab mita do (warna purana jawab dohraata)
    try:
        reply = _answer(message)
        return _memory_ack(message, reply)
    except tools.DirectReply as d:
        # Tool ne seedha jawab diya (jaise "cancel kar diya") - AI ke paas wapas nahi gaya
        ui.log(f"Direct reply from tool during {last_brain} (no extra AI call)")
        _remember(message, d.reply)
        return d.reply
    finally:
        tools.current_request = ""     # Agle message tak koi khatarnak tool nahi chal sakta
        # Agla "galat hai"/"haan" tabhi memory pe lagega jab YE jawab memory ka tha
        memory.recent = memory.touched


_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _memory_ack(message, reply):
    """Agar is sawaal mein SIRF memory tools chale (save/delete), to AI ke jawab ki
    jagah apna saaf jawab do - exact save hui baat + username/ID ki spelling +
    "Sahi hai?" (read-back). Isse galat suna gaya naam turant pakad mein aata hai."""
    names = {name for name, _ in tools.call_log}
    if not reply or not names or not names <= {"save_memory", "delete_memory"}:
        return reply
    if last_brain not in ("gemini", "groq"):
        return reply        # Shortcut ne khud read-back bana diya hai
    clean = shortcuts._clean(message)
    # Memory wale Hinglish words bhi gino ("bhul jao", "yaad rakhna", "wali baat")
    hi = (bool(_DEVANAGARI.search(message)) or shortcuts._hinglish(clean) or bool(set(clean.split()) & {
        "yaad", "yad", "rakhna", "rakho", "bhul", "bhool", "jao", "wali", "wala", "baat",
        "mera", "meri", "mere", "mujhe", "hai", "ka", "ki"}))

    parts = []
    for name, result in tools.call_log:
        result = str(result)
        if result.startswith("Saved to memory: "):
            parts.append(memory.readback(result.split(": ", 1)[1], "Yaad rakh liya", "I'll remember", hi))
        elif result.startswith("Updated memory: "):
            parts.append(memory.readback(result.split(" -> ", 1)[1], "Update kar diya", "Updated", hi))
        elif result.startswith("Already in memory: "):
            parts.append(memory.readback(result.split(": ", 1)[1], "Ye pehle se yaad hai", "I already know", hi))
        elif result.startswith("Deleted all"):
            parts.append("Saari memory mita di." if hi else "I've cleared all memories.")
        elif result.startswith("Deleted from memory: "):
            fact = memory.you(result.split(": ", 1)[1])
            parts.append(f"Bhool gaya: {fact}." if hi else f"Forgotten: {fact}.")
        elif result.startswith("Nothing in memory matched"):
            parts.append("Memory mein aisa kuch nahi mila." if hi else "I found nothing like that in memory.")
        else:
            return reply        # Error/BLOCKED - AI ka jawab hi theek hai
    fixed = ("Theek hai sir. " if hi else "Okay sir. ") + " ".join(parts)
    ui.log("Memory reply from code (exact read-back)")
    if history and history[-1]["role"] == "assistant":
        history[-1]["text"] = fixed
    return fixed


# Google kabhi akshar ko uske NAAM se likhta hai: K -> "Ke", R -> "ar", S -> "es".
# Ye sirf spelling ke BEECH (akele aksharon ke saath) akshar maane jaate hain, warna
# "uske baad" jaisa normal Hindi "ke" chhed dete.
_LETTER_NAMES = {"ke": "k", "kay": "k", "ar": "r", "are": "r", "es": "s", "ess": "s",
                 "aye": "a", "ay": "a", "bee": "b", "dee": "d", "gee": "g", "jay": "j",
                 "el": "l", "em": "m", "en": "n", "pee": "p", "cue": "q", "tee": "t",
                 "vee": "v", "ex": "x", "zed": "z", "zee": "z", "eye": "i"}


def _is_single(tok):
    return len(tok) == 1 and tok.isalnum()


def join_spelled(text):
    """Spell kiya hua naam/ID jodo: "k r r i s h 972" -> "krrish972",
    "Ke r r i s h" -> "krrish". 3+ akele akshar/ank lagatar hon tabhi jodte hain
    ("I am a boy" nahi chhedta), aur unke turant baad aaya number bhi jud jaata hai."""
    toks = text.split()
    out, i = [], 0
    while i < len(toks):
        j = i
        run = []
        while j < len(toks):
            t = toks[j]
            low = t.lower()
            if _is_single(t):
                run.append(t)
            elif low in _LETTER_NAMES and (
                    (j + 1 < len(toks) and (_is_single(toks[j + 1]) or toks[j + 1].lower() in _LETTER_NAMES))
                    or (run and _is_single(run[-1]))):
                run.append(_LETTER_NAMES[low])       # Spelling ke beech "Ke" -> "k"
            else:
                break
            j += 1
        if len(run) >= 3:
            word = "".join(run)
            if j < len(toks) and toks[j].isdigit():  # "krrish 972" -> "krrish972"
                word += toks[j]
                j += 1
            out.append(word)
            i = j
        else:
            out.append(toks[i])
            i += 1
    return " ".join(out)


def ends_mid_spelling(text):
    """Suna hua text akele akshar pe khatam hua? ("...Hai Ke r r i") - matlab aap
    abhi spelling bol rahe the aur pause pe recording ruk gayi."""
    # Sirf AKSHAR pe khatam ho tab (number pe nahi - "...s h 9 7 2" poora ho chuka hai)
    toks = text.split()
    return len(toks) >= 2 and _is_single(toks[-1]) and toks[-1].isalpha() and (
        _is_single(toks[-2]) or toks[-2].lower() in _LETTER_NAMES)


def continues_spelling(text):
    """Naya suna hissa spelling ka hi aage ka hai? (akele akshar/ank ya akshar ke naam se shuru)"""
    toks = text.split()
    return bool(toks) and (_is_single(toks[0]) or toks[0].isdigit() or toks[0].lower() in _LETTER_NAMES)


def _gemini_all_models(message, out):
    """Worker thread: models ko order mein try karo. out["reply"] mein jawab ya out["done"] = True."""
    for model in _gemini_models_up():
        try:
            out["reply"] = _tidy(_ask_gemini(message, model))
            out["model"] = model
            break
        except Exception as e:
            code = getattr(e, "code", None)
            print(f"  (Gemini {model} error {code or ''}: {str(e)[:100]})")
            _model_failed(model, code)          # Ye model kuch der ke liye skip
            if tools.call_log:                  # Tool chal chuka hai -> dusra Gemini nahi, Groq note ke saath
                break
    out["done"] = True


def _gemini_with_deadline(message):
    """Gemini ko GEMINI_BUDGET_SECONDS milte hain (tool chal gaya ho to zyada, max 12s). Jawab ya None.
    Der ho to thread chhod dete hain (uska jawab ignore) aur seedha Groq."""
    out = {}
    t = threading.Thread(target=_gemini_all_models, args=(message, out), daemon=True)
    started = time.time()
    t.start()
    while not out.get("done"):
        waited = time.time() - started
        limit = 12 if tools.call_log else GEMINI_BUDGET_SECONDS
        if waited > limit:
            print(f"  (Gemini {waited:.1f}s mein nahi aaya -> Groq)")
            out["abandoned"] = True
            return None
        time.sleep(0.05)
    if out.get("reply"):
        ui.log(f"Brain: Gemini ({out['model']})")
        return out["reply"]
    return None


def _answer(message):
    """ask() ka asli kaam: shortcut -> Gemini -> Groq."""
    global last_brain

    _start_daily_probe()

    # --- 1. Simple command? Bina AI ke seedha chalao (requests bachti hain) ---
    last_brain = "shortcut"      # (pehle set - taaki DirectReply aaye to pata rahe kisne chalaya)
    reply = shortcuts.handle(message)
    if reply:
        last_brain = "shortcut"
        ui.log("Brain: shortcut (no AI)")
        _remember(message, reply)
        return reply

    # --- 2. Gemini (main brain) ---
    tools.call_log.clear()       # Is sawaal mein kaunse tools chale, yahan jama honge
    if gemini_available():
        last_brain = "gemini"
        reply = _gemini_with_deadline(message)
        if reply is not None:
            last_brain = "gemini"
            _remember(message, reply)
            return reply
        if groq_client:
            ui.log("Switched to backup brain")

    # --- 3. Groq (backup brain) ---
    if not groq_client:
        return "Sorry sir, Gemini abhi kaam nahi kar raha aur backup brain set nahi hai."

    # Agar Gemini fail hone se pehle koi tool chala chuka tha (jaise app khol di),
    # to Groq ko bata do taaki wo dobara na chalaye
    note = ""
    if tools.call_log:
        done = "; ".join(f"{name} -> {result}" for name, result in tools.call_log)
        note = f"\n\n(Note: these tools already ran for this request, do not run them again: {done})"

    last_brain = "groq"
    try:
        reply = _tidy(_ask_groq(message, note))
    except Exception as e:
        print(f"  (Groq error: {str(e)[:200]})")
        return "Sorry sir, dono brains abhi kaam nahi kar rahe. Thodi der baad try kariye."
    last_brain = "groq"
    ui.log(f"Brain: Groq ({GROQ_MODEL})")
    _remember(message, reply)
    return reply
