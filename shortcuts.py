# ============================================
# shortcuts.py - Simple commands bina AI ke (Gemini/Groq ki requests bachti hain)
#   time/date, battery/system, volume/mute, app ya website kholna,
#   PC shutdown/restart (confirmation ke saath)
#
# Har pattern POORE command se match hota hai (sirf ek word nahi), taaki
# "match kis time shuru hoga" jaisa sawaal galti se "time" shortcut na bane -
# wo AI ke paas jaayega. Match na ho to handle() None deta hai -> AI sambhalega.
# ============================================

import os
import re          # Patterns (regex) se command pehchanne ke liye

import tools       # Asli kaam tools karte hain (UI log + try/except + DRY_RUN wahi hai)


# Ye words dikhe to jawab Hinglish mein do, warna English mein
HINGLISH_HINTS = {"kya", "hai", "batao", "kitne", "kitni", "kitna", "baje", "aaj", "karo",
                  "kar", "do", "kholo", "khol", "tarikh", "taarikh", "tareekh", "samay",
                  "waqt", "din", "awaaz", "band", "chalu", "ko", "pe", "par", "hua", "raha",
                  "bachi", "kaun", "kaunsa", "konsi"}


def _clean(text):
    """Lowercase, punctuation hatao, aage-peeche ka 'jarvis'/'please' hatao."""
    text = re.sub(r"[?.,!।]", " ", text.lower())
    # "Jarvis" aur uske galat sune roop (Google kabhi "jervis"/"service" sun leta hai)
    text = re.sub(r"^\s*(hey\s+)?(jarvis|jervis|jarvi|jarvish|javis|travis|service|जार्विस)\s+", "", text)
    text = re.sub(r"\b(please|plz|zara)\b", " ", text)
    return " ".join(text.split())


def _hinglish(text):
    """Hinglish word ya Devanagari (हिंदी) letters hon to True."""
    return bool(set(text.split()) & HINGLISH_HINTS) or bool(re.search(r"[ऀ-ॿ]", text))


# ============================================
# Time / date / battery: "keyword + filler" tareeka
#   Command mein kam se kam ek KEYWORD ho (jaise tarikh, samay, battery), aur
#   baaki SAARE words FILLER hon (kya, hai, batao, abhi...). Koi aur word aaya
#   (jaise "match kis time SHURU hoga", "time TABLE bana do") to shortcut nahi,
#   AI ke paas jaayega.
# ============================================
FILLER = {
    # Hinglish
    "abhi", "kya", "hai", "hain", "hua", "hue", "ho", "raha", "rahe", "gaya", "gaye",
    "batao", "bata", "bataiye", "do", "kitna", "kitni", "kitne", "ka", "ki", "ke",
    "aaj", "kaun", "kaunsa", "kaun-sa", "konsa", "konsi", "sa", "si", "sir", "mujhe",
    "bachi", "bacha", "mein", "me", "kaisa", "kaisi", "check", "karo", "kar",
    # English
    "what", "what's", "whats", "is", "it", "the", "now", "current", "today", "today's",
    "todays", "tell", "me", "how", "much", "left", "do", "i", "have", "my", "status",
    "level", "usage", "info", "percent", "percentage",
    # Devanagari (Google hi-IN se aisa text aata hai)
    "अभी", "क्या", "है", "हैं", "हुआ", "हो", "रहा", "रहे", "बताओ", "बताइए", "कितना",
    "कितनी", "कितने", "आज", "की", "का", "के", "कौन", "सा", "सी", "मेरी", "में",
}
TIME_KEYS = {"time", "samay", "samai", "waqt", "vakt", "baje", "बजे", "समय", "वक्त", "टाइम"}
DATE_KEYS = {"date", "tarikh", "taarikh", "tareekh", "tarik", "din", "day",
             "तारीख", "तारीख़", "दिन", "डेट"}
SYSTEM_KEYS = {"battery", "cpu", "ram", "system", "charge", "charging", "बैटरी"}


def _is(text, keys):
    """True agar command mein koi key ho aur baaki sab filler words hon."""
    words = set(text.split())
    return bool(words & keys) and words <= (keys | FILLER)


VOLUME = re.compile(
    r"(set )?(the )?volume (to |ko )?(?P<n>\d{1,3})( ?%| percent)?( (pe|par))?"
    r"( (kar do|karo|kardo|set karo|set kar do))?")
MUTE = re.compile(r"mute( karo| kar do| kardo)?|(awaaz|sound) band (karo|kar do)")
UNMUTE = re.compile(r"unmute( karo| kar do| kardo)?|(awaaz|sound) (chalu|on) (karo|kar do)")
OPEN_EN = re.compile(r"open (the )?(?P<name>.+?)( app)?")
OPEN_HI = re.compile(r"(?P<name>.+?) (kholo|khol do|open karo|open kar do|chalu karo|start karo)")

# ============================================
# Media keys / relative volume / brightness (bina AI)
#   Sab POORE command se match hote hain (fullmatch), taaki "next match kab hai" jaisa
#   sawaal, ya "brightness kya hai" (get) galti se shortcut na bane.
# ============================================
_GAANA = r"(?:gaana|gana|gane|gaane|song|songs|music|track|video|गाना|संगीत)"
_KARO = r"(?:karo|kar do|kardo|kar de|do)"
_CHALAO = r"(?:chalao|chala do|chala|sunao|suno|play karo|baja do|chalao ja)"

MEDIA_PLAY_PAUSE = re.compile(
    rf"(?:{_GAANA} )?(?:play|pause|chalu|resume)(?: {_KARO})?(?: {_GAANA})?"
    rf"|(?:play|pause) (?:the )?(?:music|song|gaana|playback|video|media)(?: {_KARO})?")
MEDIA_NEXT = re.compile(
    rf"(?:next|agli|agla|agale|aage|aage wala)(?: ka| ki| wala| wali)? (?:{_GAANA} )?(?:{_GAANA})"
    rf"(?: (?:{_CHALAO}|{_KARO}))?")
MEDIA_PREVIOUS = re.compile(
    rf"(?:pichla|pichli|pichle|pehla|pehli|previous|last wala|agle pichle)(?: ka| ki| wala| wali)? "
    rf"(?:{_GAANA} )?(?:{_GAANA})(?: (?:{_CHALAO}|{_KARO}))?")
MEDIA_STOP = re.compile(
    # "gaana roko" / "music band karo" / "rok do gaana" - media word dono taraf zaroori
    rf"(?:roko|rok do|rok|banda karo|band karo|band kar do|chup karo) (?:the )?(?:{_GAANA}|music|playback|video)"
    rf"|(?:{_GAANA}) (?:roko|rok do|rok|banda karo|band karo|band kar do|chup karo)")

# "awaaz badhao" / "awaaz kam karo" (set_volume "volume 50" wala alag hai)
_AWAAZ = r"(?:awaaz|awaz|aawaz|volume|sound|आवाज़|आवाज)"
VOL_UP = re.compile(
    rf"{_AWAAZ} (?:badhao|badha do|badha|badhana|zyada|tez|increase|up)(?: {_KARO})?"
    rf"|(?:badhao|badha do|increase|up|turn up) (?:the )?{_AWAAZ}")
VOL_DOWN = re.compile(
    rf"{_AWAAZ} (?:kam|ghatao|ghata|ghata do|dheere|down|decrease)(?: {_KARO})?"
    rf"|(?:kam|ghatao|ghata|decrease|down|turn down) (?:the )?{_AWAAZ}")

# "brightness kam karo" / "brightness zyada karo" / "brightness 50 karo"
_SCREEN_LIGHT = r"(?:brightness|brightnes|roshni|roshniyan|dim|bright|ब्राइटनेस|रोशनी)"
BRIGHTNESS_SET = re.compile(
    rf"{_SCREEN_LIGHT} (?:ko |to |par )?(?P<n>\d{{1,3}})\s*(?:%|percent)?(?: {_KARO})?")
BRIGHTNESS_UP = re.compile(
    rf"{_SCREEN_LIGHT} (?:zyada|badhao|badha|increase|up|full)(?: {_KARO})?"
    rf"|(?:badhao|badha|increase|up) (?:the )?{_SCREEN_LIGHT}(?: {_KARO})?")
BRIGHTNESS_DOWN = re.compile(
    rf"{_SCREEN_LIGHT} (?:kam|ghatao|ghata|dheere|down|low|minimum|zero)(?: {_KARO})?"
    rf"|(?:kam|ghatao|ghata) (?:the )?{_SCREEN_LIGHT}(?: {_KARO})?")

# Weather: "delhi ka weather kaisa hai", "mumbai mein mausam kya hai", "weather in pune"
# Google "weather" ko kabhi "vedar"/"whether" sun leta hai - wo sab bhi pakdo
WEATHER_WORD = r"(weather|wether|whether|vedar|vether|wedar|wheather|mausam|mosam|temperature|temp)"
WEATHER_HI = re.compile(
    rf"(?P<city>[a-z][a-z ]*?) (ka|ki|mein|me|main) {WEATHER_WORD}"
    r"( (kaisa|kya|kitna))?( (hai|rahega|hoga))?( (batao|bata do|search karo|check karo))?")
WEATHER_EN = re.compile(
    rf"((what's|whats|what is|how's|hows|how is) )?(the )?{WEATHER_WORD}( like)? in "
    r"(?P<city>[a-z][a-z ]*?)( today| now| right now)?")

# PC band / restart - seedha tool (tool khud "Sir, pakka?" poochhta hai, DRY_RUN bhi wahi)
PC = r"(my |the |mera |apna )?(pc|computer|laptop|system|कंप्यूटर|पीसी)( ko)?"
PC_SHUTDOWN = re.compile(
    rf"({PC} (shutdown|shut down|band|off)( karo| kar do| kardo| kar de)?)"
    rf"|((shutdown|shut down|turn off|switch off) {PC})")
PC_RESTART = re.compile(
    rf"({PC} (restart|reboot)( karo| kar do| kardo| kar de)?)|((restart|reboot) {PC})")


def _open(name):
    """App ya website kholo - sirf tab jab naam jaani-pehchani list mein ho."""
    site_key = name.replace("web", "").replace(".com", "").strip()
    if name in tools.APPS:
        result = tools.open_app(name)
    elif site_key in tools.WEBSITES:
        result = tools.open_website(name)
    else:
        return None                   # Anjaan naam -> AI ko dene do
    if result.startswith("Error"):
        return f"Sorry sir, {name} nahi khul paya. {result}"
    return result


def _asks_memory(text):
    """"Mere baare mein kya jaante ho?" / "what do you know about me" jaisa sawaal?"""
    words = set(text.split())
    if text in ("what do you know about me", "what do you remember about me",
                "meri memory batao", "meri memories batao", "meri saari memories batao"):
        return True
    return (len(words) <= 9 and bool(words & {"mere", "mujhe", "mera"})
            and bool(words & {"baare", "bare", "baarein"})
            and bool(words & {"jaante", "jante", "jaanti", "pata", "yaad"}))


# "screen pe kya hai" jaise seedhe sawaal -> bina main AI ke seedha vision tool
SCREEN_ASK = re.compile(
    r"((meri |is |iss )?screen (pe|par|mein|me) kya (hai|dikh raha hai|chal raha hai))"
    r"|((meri )?screen dekho)|(what'?s on (my |the )?screen)|(look at (my |the )?screen)"
    r"|((screen (pe|par|mein|me) )?(ka |wala |wale |ye |yeh |is |iss )?error (ko )?"
    r"(samjhao|samjha do|samjha de|explain karo|explain kar do))")


# ============================================
# MEMORY commands (bina AI) - exact save, correction, list, number se delete
# ============================================
# Type karke exact save: "remember: GitHub = KRRISH972" / "yaad rakhna: ..."
TYPED_REMEMBER = re.compile(r"\s*(remember|yaad rakhna|yaad rakho|yad rakhna|save|memory)\s*:\s*(?P<fact>.+)",
                            re.IGNORECASE)
YES = {"haan", "han", "ha", "haa", "yes", "yeah", "sahi", "correct", "bilkul", "right", "ok", "okay", "theek"}
NO = {"nahi", "nahin", "no", "galat", "wrong", "नहीं", "गलत"}
# Aakhri memory galat hai -> hatao ("galat hai", "nahi ye nahi", "ye sahi nahi hai")
WRONG = re.compile(r"((ye |yah |woh? )?(galat|wrong)( hai| tha)?)|(nahi+n?,? ?(ye|yah) nahi+n?( hai)?)|"
                   r"((ye |yah )?sahi nahi+n?( hai)?)|(nahi+n?( nahi+n?)?)")
# Aakhri memory ke peeche kuch jodo: "iske peeche 972 bhi hai", "uske baad 972 aur hai"
APPEND = re.compile(r"(ye |yah )?(iske|uske|isme|usme|is ke|us ke) (peeche|piche|pichhe|baad|end mein|aakhir mein|aage) "
                    r"(?P<x>[a-z0-9@._]+) (bhi |aur )?(hai|lagao|jodo|add karo|laga do)?")
SHOW_MEMORY = re.compile(r"((meri |saari |sab )?(memory|memories|yaadein)( list)? (dikhao|batao|show karo|list karo))|"
                         r"(show (my )?(memory|memories))|(list (my )?(memory|memories))|(memory list)")
DELETE_NUM = re.compile(r"(memory|memories)( number| no| nambar)? (?P<n>\w+)( number| wali)? (hatao|hata do|delete karo|delete kar do|mitao|remove karo)|"
                        r"(delete|remove) memory( number)? (?P<n2>\w+)|(?P<n3>\w+) (number|no) (memory|wali memory) (hatao|delete karo|mitao)")
NUM_WORDS = {"ek": 1, "one": 1, "do": 2, "two": 2, "teen": 3, "three": 3, "char": 4, "chaar": 4, "four": 4,
             "paanch": 5, "panch": 5, "five": 5, "chhe": 6, "chhah": 6, "six": 6, "saat": 7, "seven": 7,
             "aath": 8, "eight": 8, "nau": 9, "nine": 9, "das": 10, "ten": 10}


def _undo_reply(memory):
    """"Galat hai" -> aakhri badlaav palto. Update tha to PURANI value wapas aati hai
    (sahi username galti se kho na jaaye), naya save tha to hat jaata hai."""
    result = memory.undo_last()
    if not result:
        return None
    kind, fact = result
    if kind == "restored":
        return f"Theek hai sir, wapas purana kar diya: {memory.you(fact)}."
    return (f"Theek hai sir, hata diya: {memory.you(fact)}. Sahi wala dobara boliye, "
            f"ya type karke likhiye: remember: ...")


def _memory_command(command, text, hi):
    """Memory wale commands. Jawab (text) ya None."""
    import memory

    # --- Type karke exact save (jaise likha waise hi, case bhi same) ---
    m = TYPED_REMEMBER.fullmatch(command.strip())
    if m:
        status, old = memory.add(m["fact"].strip())
        if status == "updated":
            return memory.readback(m["fact"].strip(), "Update kar diya", "Updated", hi)
        if status == "same":
            return memory.readback(m["fact"].strip(), "Ye pehle se yaad hai", "I already know", hi)
        return memory.readback(m["fact"].strip(), "Yaad rakh liya", "I'll remember", hi)

    # --- "Memory dikhao" -> terminal mein number ke saath poori list ---
    if SHOW_MEMORY.fullmatch(text):
        items = memory.numbered()
        print(f"\n  ===== JARVIS memory ({len(items)}) - file: {memory.MEMORY_FILE} =====")
        for n, fact in items:
            print(f"  {n}. {fact}")
        print("  ('memory 2 hatao' bolke/likh ke hata sakte ho, ya file VS Code mein edit karo)\n")
        if not items:
            return "Sir, abhi memory khaali hai." if hi else "Sir, memory is empty."
        return (f"Sir, {len(items)} baatein yaad hain, terminal mein number ke saath dikha di." if hi
                else f"Sir, I remember {len(items)} things - listed in the terminal.")

    # --- "Memory 3 hatao" ---
    m = DELETE_NUM.fullmatch(text)
    if m:
        word = m["n"] or m["n2"] or m["n3"]
        n = int(word) if word.isdigit() else NUM_WORDS.get(word)
        if n is not None:
            removed = memory.remove_number(n)
            if removed is None:
                return f"Sir, memory number {n} hai hi nahi. 'Memory dikhao' bolke list dekh lijiye."
            return f"Theek hai sir, memory {n} hata di: {memory.you(removed)}."

    # --- Read-back ke baad "Sahi hai?" ka jawab ---
    words = set(text.split())
    if memory.recent and memory.awaiting_check and len(words) <= 4:
        memory.awaiting_check = False
        if words & NO:
            reply = _undo_reply(memory)
            if reply:
                return reply
        elif words & YES:
            memory.touched = True
            return "Theek hai sir." if hi else "Great, sir."

    # --- Correction (sirf jab pichla jawab memory ka tha) ---
    if memory.recent and memory.last_fact:
        m = APPEND.fullmatch(text)
        if m:
            changed = memory.append_to_last(m["x"])
            if changed:
                return memory.readback(changed[1], "Update kar diya", "Updated", hi)
        if WRONG.fullmatch(text):
            reply = _undo_reply(memory)
            if reply:
                return reply
    return None


# ============================================
# WHATSAPP / CALL commands (bina AI) - asli kaam tools karte hain (confirm + DRY_RUN + lock)
# ============================================
_TO = r"(?P<c>[\w .]+?) ko"
WA_SEND = re.compile(
    _TO + r" (?:whatsapp (?:pe |par )?)?(?:message |msg |whatsapp )?"
    r"(?:bhejo|bhej do|send karo|send kar do|likh do|bol do|keh do|bata do)(?:,)? (?:ki |that )?(?P<m>.+)"
    r"|send (?:a )?(?:whatsapp )?(?:message|msg) to (?P<c2>[\w .]+?) (?:saying|that) (?P<m2>.+)"
    # "mujhe message bhejo ki ..." / "khud ko bhejo ..." -> apni (You) chat
    r"|(?P<c3>mujhe|mujhko|khud ko|apne aap ko) (?:whatsapp )?(?:message |msg )?"
    r"(?:bhejo|bhej do|send karo|send kar do)(?:,)? (?:ki |that )?(?P<m3>.+)", re.IGNORECASE)
WA_CALL = re.compile(
    _TO + r" (?P<w>whatsapp )?(?P<v>video )?(?P<k>call|phone call|phone|audio call|voice call) "
    r"(?:karo|kar do|lagao|laga do|milao|mila do)"
    r"|(?P<v2>video )?call (?P<c2>[\w ]+)", re.IGNORECASE)
WA_END = re.compile(r"(?:call|phone) (?:kaat|kat|kaato|cut|end|band|rakh|disconnect)(?: do| karo| kar do| de)?"
                    r"|(?:end|cut|hang up)(?: the)? call", re.IGNORECASE)
WA_READ = re.compile(r"(?:whatsapp )?(?:messages?|msgs?) (?:padho|padh do|sunao|suna do|batao|read karo|check karo)"
                     r"|(?:read|check)(?: my)?(?: whatsapp)? messages"
                     r"|koi (?:naya )?(?:whatsapp )?message (?:aaya|hai)(?: kya)?(?: hai)?", re.IGNORECASE)
WA_REPLY = re.compile(r"(?:(?:haan|ha|han|yes|ok)[, ]+)?(?:reply (?:karo|kar do)|bol do|likh do|keh do|bata do|bhej do)"
                      r"(?:,)? (?:ki |that )?(?P<m>.+)", re.IGNORECASE)


def _raw(command):
    """Case bacha ke (message ka text jaisa bola waisa), sirf 'jarvis' aur end ka ?.! hatao."""
    raw = re.sub(r"^\s*(hey\s+)?(jarvis|jervis|jarvi|service)\W*\s*", "", command, flags=re.IGNORECASE)
    return raw.strip(" .!?।")


def _whatsapp_command(command, text):
    """WhatsApp/call wale seedhe commands. Jawab (text) ya None. Tools DirectReply se jawab dete hain."""
    import notifications
    raw = _raw(command)

    if WA_END.fullmatch(raw):
        return tools.end_call()
    if WA_READ.fullmatch(raw):
        return tools.read_messages()

    # "Reply karun?" ke baad: "haan, bol do ki pakka" / "nahi"
    if notifications.last_sender:
        m = WA_REPLY.fullmatch(raw)
        if m and not WA_SEND.fullmatch(raw):
            notifications.awaiting_reply = False
            return tools.send_whatsapp(notifications.last_sender, m["m"].strip())
        if notifications.awaiting_reply:
            words = set(text.split())
            if words and words <= YES | {"reply", "karo", "kar", "do"}:
                return "Kya reply karun, sir? Boliye jaise: 'bol do ki pakka'."
            notifications.awaiting_reply = False
            if words & NO and len(words) <= 3:
                return "Theek hai sir, reply nahi karta."

    m = WA_SEND.fullmatch(raw)
    if m:
        if m["c3"]:
            contact, message = "khud", m["m3"].strip()          # Apni (You) chat
        else:
            contact, message = (m["c"] or m["c2"]).strip(), (m["m"] or m["m2"]).strip()
        return tools.send_whatsapp(contact, message)

    m = WA_CALL.fullmatch(raw)
    if m:
        # "call karo" / "phone karo" dono = WhatsApp call ("video" ho to video call)
        contact = (m["c"] or m["c2"] or "").strip()
        return tools.whatsapp_call(contact, video=bool(m["v"] or m["v2"]))
    return None


# ============================================
# Media keys / volume relative / brightness commands (bina AI)
#   Poora command match hona zaroori (fullmatch) - "next match kab hai" jaisa sawaal
#   ya "brightness kya hai" (get) shortcut nahi banna chahiye, wo AI ke paas jaaye.
# ============================================
def _tool_reply(result, hi, yes_hi, yes_en):
    """Tool ka result check karo: error / DRY_RUN / confirm line.

    Hinglish ya English confirm line bhi de deta hai (test mode mein 'Sir, test mode...' -
    asli kaam nahi hua, ye saaf batana zaroori hai)."""
    text = str(result)
    if text.startswith(("Error", "Could not", "BLOCKED")):
        return f"Sorry sir, {text}"
    if text.startswith("DRY RUN"):
        return "Sir, test mode hai, isliye ye kaam sach mein nahi hua."
    return yes_hi if hi else yes_en


# ============================================
# Files: "downloads mein latest pdf kholo", "resume file dhoondo", "pehli wali kholo"
#   Sab fullmatch. "chrome kholo" jaisa app command yahan nahi aata: kholne wale command
#   mein folder ya "latest" ya file-type zaroor chahiye (code mein check hota hai).
# ============================================
_F_DIR = r"(?:downloads?|documents?|desktop|pictures?)"
_F_TYPE = r"(?:pdf|word|excel|ppt|powerpoint|image|photo|video|zip|txt|file)"
_F_LATEST = r"(?:latest|naya|nayi|newest|recent|sabse naya|sabse nayi)"
_F_OPEN = r"(?:kholo|khol do|khol de|open karo|open kar do)"
_F_NUM = r"(?:\d|pehl[ai]|dusr[ai]|doosr[ai]|teesr[ai]|chauth[ai]|first|second|third|fourth|fifth)"
FILE_OPEN_HI = re.compile(
    rf"(?:(?P<f1>{_F_DIR}) (?:mein|me|se|ki|ka|ke) )?(?:(?P<lat>{_F_LATEST}) )?(?P<type>{_F_TYPE})"
    rf"(?: file)?(?: (?P<f2>{_F_DIR}) (?:mein|me|se|wali|wala|ki|ka))? {_F_OPEN}")
FILE_OPEN_EN = re.compile(
    rf"open (?:the |my )?(?:(?P<lat>{_F_LATEST}) )?(?P<type>{_F_TYPE})(?: file)?"
    rf"(?: (?:in|from) (?:the |my )?(?P<f2>{_F_DIR})(?: folder)?)?")
FILE_FIND_HI = re.compile(
    rf"(?:(?P<f>{_F_DIR}) (?:mein|me|ki|ka) )?(?P<q>.+?) (?:file |files )?"
    rf"(?:dhoondo|dhundo|dhoondh do|dhundh do|find karo|search karo)")
FILE_FIND_EN = re.compile(
    rf"(?:find|search for) (?:the |my )?(?P<q>.+?)(?: (?:in|from) (?:the |my )?(?P<f>{_F_DIR})(?: folder)?)?")
FILE_PICK = re.compile(
    rf"(?:(?:file|number|no) )?(?P<n>{_F_NUM})(?: wali| wala| number)*(?: file)? {_F_OPEN}"
    rf"|open (?:the )?(?:file )?(?:number )?(?P<n2>{_F_NUM})(?: file)?")


def _file_names_reply(hi):
    """Pichle find_files ke naam bolne layak (numbered) - kaunsi kholun poochne ke liye."""
    base = [os.path.splitext(os.path.basename(p))[0] for p in tools.last_files]
    # Same naam do baar ho to folder ka naam jodo (Downloads / Desktop) taaki farak pata chale
    names = [f"{i}. {b}" + (f" ({os.path.basename(os.path.dirname(p))})" if base.count(b) > 1 else "")
             for i, (b, p) in enumerate(zip(base, tools.last_files), 1)]
    return "; ".join(names[:5])


def _files_command(text, hi):
    """File dhoondho / kholo (bina AI). Jawab (text) ya None (AI ke paas jaao)."""
    # --- "pehli wali kholo" / "file 2 kholo": sirf jab pehle koi list bani ho ---
    m = FILE_PICK.fullmatch(text) if tools.last_files else None
    if m:
        result = tools.open_file(m["n"] or m["n2"])
        return _tool_reply(result, hi, "File khol di, sir.", "Opened the file, sir.")

    # --- "downloads mein latest pdf kholo" ---
    m = FILE_OPEN_HI.fullmatch(text) or FILE_OPEN_EN.fullmatch(text)
    if m and (m["lat"] or m["f2"] or ("f1" in m.groupdict() and m["f1"])):
        folder = m["f2"] or (m.groupdict().get("f1"))
        kind = "" if m["type"] == "file" else m["type"]
        result = tools.find_files(" ".join(x for x in (folder, m["lat"], kind) if x))
        if result.startswith(("Error", "Could not", "BLOCKED")):
            return f"Sorry sir, {result}"
        if not tools.last_files:
            return "Sir, aisi koi file nahi mili." if hi else "I couldn't find such a file, sir."
        if m["lat"] or len(tools.last_files) == 1:       # "latest" = sabse nayi ek hi file
            result = tools.open_file("1")
            return _tool_reply(result, hi, "File khol di, sir.", "Opened the file, sir.")
        return (f"Sir, {len(tools.last_files)} files mili: {_file_names_reply(hi)}. Kaunsi kholun?"
                if hi else f"I found {len(tools.last_files)} files: {_file_names_reply(hi)}. Which one?")

    # --- "resume file dhoondo" / "find resume file" ---
    m = FILE_FIND_HI.fullmatch(text) or FILE_FIND_EN.fullmatch(text)
    if m:
        q = " ".join(x for x in (m["f"], m["q"]) if x)
        hint = set(q.split()) & {"file", "files", "pdf", "word", "excel", "ppt", "powerpoint", "image",
                                 "photo", "video", "zip", "txt", "downloads", "download", "documents",
                                 "document", "desktop", "pictures", "picture"}
        if hint or "file" in text.split() or "files" in text.split():
            result = tools.find_files(q)
            if result.startswith(("Error", "Could not", "BLOCKED")):
                return f"Sorry sir, {result}"
            if not tools.last_files:
                return "Sir, aisi koi file nahi mili." if hi else "I couldn't find such a file, sir."
            return (f"Sir, {len(tools.last_files)} files mili: {_file_names_reply(hi)}. Kaunsi kholun?"
                    if hi else f"I found {len(tools.last_files)} files: {_file_names_reply(hi)}. Which one?")
    return None


# ============================================
# Notes: "note likho: kal Rahul se milna hai", "mere notes padho", "note 2 hata do"
#   Sab fullmatch. "note kya hota hai" / "notes app kholo" shortcut nahi bante.
#   Note ka text lowercase nahi hona chahiye, isliye add ke liye asli command use hota hai.
# ============================================
NOTE_LIST = re.compile(
    r"(?:(?:mere|meri|saare|sab) )?notes?(?: (?:ko))? (?:padho|padh do|padh ke sunao|sunao|dikhao|batao)"
    r"|read (?:my |the )?notes|(?:mere )?notes? kya kya hain")
NOTE_DELETE = re.compile(
    r"notes? (?P<n>\d{1,3}) (?:hata do|hatao|hata de|delete karo|delete kar do|mita do|remove karo)"
    r"|(?:delete|remove) (?:the )?note (?P<n2>\d{1,3})")


def _notes_command(command, text, hi):
    """Note likhna / padhna / hatana (bina AI). Tools khud DirectReply + confirm sambhalte hain.
    Jawab (text) ya None (AI ke paas jaao)."""
    m = tools.NOTE_ADD_RX.match(command or "")
    if m:
        result = tools.note_add(m["t"])      # Sahi chale to DirectReply uthta hai (read-back)
        return f"Sorry sir, {result}"        # Yahan sirf error / BLOCKED pe pahunchte hain
    if NOTE_LIST.fullmatch(text):
        return f"Sorry sir, {tools.notes_list()}"
    m = NOTE_DELETE.fullmatch(text)
    if m:
        return f"Sorry sir, {tools.note_delete(int(m['n'] or m['n2']))}"
    return None


# ============================================
# Reminders / tasks: "10 minute baad yaad dilana ki ...", "meri tasks dikhao", "task 2 hata do",
#   "sab reminders hata do", "snooze 10 minute". Sab fullmatch / pakke pehchan wale.
# ============================================
TASK_LIST_CMD = re.compile(
    r"(?:(?:mere|meri|saare|sab|apne) )?(?:tasks?|reminders?)(?: ko)? (?:dikhao|dikha do|padho|sunao|batao|kya kya hain)"
    r"|(?:show|list) (?:my |all )?(?:tasks|reminders)")
TASK_DELETE_CMD = re.compile(
    r"(?:task|reminder) (?P<n>\d{1,3}) (?:hata do|hatao|hata de|delete karo|delete kar do|mita do|cancel karo)"
    r"|(?:delete|remove|cancel) (?:the )?(?:task|reminder) (?P<n2>\d{1,3})")
TASK_CLEAR_CMD = re.compile(
    r"(?:sab|saare|all|sabhi) (?:tasks?|reminders?|tasks aur reminders)(?: ko)? (?:hata do|hatao|mita do|delete karo|clear karo)"
    r"|(?:delete|clear|remove) all (?:tasks|reminders)")
SNOOZE_CMD = re.compile(
    r"snooze(?: (?P<d1>.+))?|(?P<d2>.+?) snooze(?: karo| kar do)?"
    r"|(?P<d3>.+? baad) phir (?:se )?(?:yaad dilana|yaad dila dena|yaad dilao)")


def _tasks_command(command, text, hi):
    """Reminders / tasks (bina AI). Tools khud confirm + DirectReply sambhalte hain.
    Jawab (text) ya None (AI ke paas jaao)."""
    import scheduler
    m = SNOOZE_CMD.fullmatch(text)
    if m:
        dur = m["d1"] or m["d2"] or m["d3"]
        minutes = 10 if not dur else scheduler.parse_duration(dur if "baad" in dur else dur + " baad")
        if minutes is not None:
            return f"Sorry sir, {tools.reminder_snooze(round(minutes))}"
    if TASK_CLEAR_CMD.fullmatch(text):
        return f"Sorry sir, {tools.tasks_clear()}"
    m = TASK_DELETE_CMD.fullmatch(text)
    if m:
        return f"Sorry sir, {tools.task_delete(int(m['n'] or m['n2']))}"
    if TASK_LIST_CMD.fullmatch(text):
        return f"Sorry sir, {tools.task_list()}"
    if scheduler.looks_like_reminder(text):
        return f"Sorry sir, {tools.reminder_add(command)}"
    return None


# ============================================
# Dev helper: "clipboard ka code samjhao", "git status batao", "aakhri 3 commits".
#   Sab fullmatch. "git kya hota hai", "code likh do" AI ke paas jaate hain.
#   Git ke write commands (commit/push/pull/reset...) NEVER: jawab "terminal se karo", koi tool nahi chalta.
# ============================================
_D_ASK = r"(?: (?:batao|bata do|bata de|dikhao|dikha do|dikha de|kya hai|dekho))?"
GIT_STATUS_CMD = re.compile(rf"(?:mera |mere |meri )?(?:git (?:ka )?status|repo (?:ka )?(?:git )?status|"
                            rf"project (?:ka )?(?:git )?status){_D_ASK}")
GIT_LOG_CMD = re.compile(rf"(?:git log|(?:aakhri|aakhiri|last|pichle|pichhle|latest|recent)(?: (?P<n>\d{{1,2}}))? commits?)"
                         rf"(?: (?P<n2>\d{{1,2}}))?{_D_ASK}")
CLIP_CMD = re.compile(r"(?:is |iss |ye |yeh )?clipboard (?:ka |ke |wala |wale |mein |me |ko )*"
                      r"(?:code |text |function )*(?:ko |mein |me )*"
                      r"(?:samjhao|samjha do|samjha de|explain karo|explain kar do|simple karo|simple kar do|"
                      r"galti(?:yan)? (?:batao|bata do|bata de))")
_G_VERB = r"(?:commit|push|pull|reset|merge|rebase|stash|revert|checkout|cherry pick|force push)"
_G_WRITE_A = re.compile(rf"git {_G_VERB}\b[\w\s.\-/]*")                      # "git push origin main"
_G_WRITE_B = re.compile(rf"\b{_G_VERB}\b")
_G_DO = re.compile(r"\b(?:kar do|kardo|karo|kar de|kar dena|kijiye|chalao|chala do|maar do|maro|now|abhi)\b")
_G_CTX = re.compile(r"\b(?:git|github|repo|repository|changes|code|branch|remote|origin|isko|ise|ye|yeh)\b")
_G_QUESTION = re.compile(r"\b(?:kya|kaun|kab|kaise|kyun|kyu|matlab|meaning|what|why|how|hota|hoti|hote|"
                         r"difference|farak|karte|karta|karti|karein|samjhao|samjha|sikhao|explain)\b")


# ============================================
# Morning briefing: "good morning", "morning briefing do", "aaj ka plan batao" (fullmatch, bina AI)
# ============================================
BRIEFING_CMD = re.compile(r"(?:good morning|gud morning|suprabhat)(?: jarvis| sir)?|"
                          r"(?:meri |mera |aaj ki |aaj ka )?(?:morning )?briefing"
                          r"(?: do| dijiye| dedo| de do| sunao| batao| bata do| suna do| chalao| shuru karo)?|"
                          r"(?:aaj ka|aaj ki|mera|meri) (?:plan|schedule|agenda)"
                          r"(?: kya hai| batao| bata do| dikhao| sunao)?")


def _dev_command(command, text, hi):
    """Dev helper (bina AI). Jawab (text) ya None. Write git commands ko NEVER-level 'nahi' deta hai."""
    if not _G_QUESTION.search(text) and (
            _G_WRITE_A.fullmatch(text)
            or (_G_WRITE_B.search(text) and _G_DO.search(text) and _G_CTX.search(text))):
        return "Ye main khud nahi karunga, sir. Isko terminal se kar lijiye."
    if GIT_STATUS_CMD.fullmatch(text):
        return f"Sorry sir, {tools.git_status()}"          # Sahi chale to DirectReply uthta hai
    m = GIT_LOG_CMD.fullmatch(text)
    if m:
        return f"Sorry sir, {tools.git_log(int(m['n'] or m['n2'] or 5))}"
    if CLIP_CMD.fullmatch(text):
        return f"Sorry sir, {tools.explain_clipboard(command)}"
    return None


# ============================================
# Content creator: "Instagram caption do: Diwali reel", "10 hashtags do: coding", "copy kar do",
#   "meri style casual rakhna", "CapCut kholo". Sawaal ("caption ka matlab kya hai") AI ke paas jaate hain.
#   Topic ke liye asli command use hota hai (bade-chhote akshar waise hi rahein).
# ============================================
_C_KW = re.compile(r"\b(captions?|hashtags?|script|title|description|hooks?)\b", re.I)
_C_VERB = re.compile(r"\b(?:do|dena|de do|de|likho|likh do|likhna|suggest(?: karo| kar do)?|batao|"
                     r"bana do|banao|chahiye|dijiye)\b", re.I)
_C_QUESTION = re.compile(r"\b(kya|kaun|kab|kaise|kyun|kyu|matlab|meaning|what|why|how|hota|hoti|hote|"
                         r"difference|farak|kitna|kitne)\b", re.I)
_C_KIND = {"caption": "caption", "captions": "caption", "hashtag": "hashtags", "hashtags": "hashtags",
           "script": "reel_script", "title": "youtube_title", "description": "youtube_description",
           "hook": "hook_ideas", "hooks": "hook_ideas"}
_C_NOISE = [re.compile(p, re.I) for p in (
    r"\b\d+\s*(?:second|sec|s)\b(?:\s*(?:ka|ki|ke))?",              # "30 second ka"
    r"\b\d+\s*hashtags?\b",                                          # "10 hashtags"
    r"\b(?:instagram|insta|youtube|yt|reel|reels|video|is|iss|ye|yeh|ek|mujhe|mere|meri|mera)\s+(?:ka|ki|ke)\b",
    r"\b(?:ke liye|ke lie|please|plz|zara|jarvis)\b")]
STYLE_CMD = re.compile(r"(?:meri|mera|apni) (?:content )?style (?P<s>.+?) (?:rakhna|rakho|rakhiye|rakh do|rakhe)")
COPY_CMD = re.compile(r"(?:isko |ise |ye |yeh |isse )?(?:clipboard mein )?copy (?:kar do|karo|kar de|kar dena)"
                      r"|copy (?:this|that|it)|clipboard mein (?:daal do|copy karo)")
_ED = r"(?:capcut|cap cut|davinci resolve|davinci|da vinci resolve|da vinci|premiere pro|premiere|adobe premiere pro|adobe premiere)"
EDITOR_CMD = re.compile(rf"(?P<e>{_ED}) (?:kholo|khol do|khol de|open karo|open kar do|chalao|start karo)"
                        rf"|open (?P<e2>{_ED})")


def _content_topic(raw, kw):
    """Command se topic nikaalo: colon ke baad ka hissa, warna keyword/verb/faltu shabd hata ke."""
    if ":" in raw:
        return raw.split(":", 1)[1].strip()
    topic = raw
    for rx in _C_NOISE:
        topic = rx.sub(" ", topic)
    topic = _C_KW.sub(" ", topic)
    topic = _C_VERB.sub(" ", topic)
    words = [w for w in topic.split() if w.lower() not in {"ka", "ki", "ke", "ko", "ek", "aur", "instagram",
                                                            "insta", "youtube", "yt"}]
    while words and words[0].lower() in {"is", "iss", "ye", "yeh"}:
        words.pop(0)              # "is video ka ..." ka bacha "is"
    return " ".join(words).strip(" :,-")


def _content_command(command, text, hi):
    """Content pack (bina AI): style save, copy, editors, caption/hashtags/script/title/... likhwana.
    Jawab (text) ya None (AI ke paas jaao)."""
    m = STYLE_CMD.fullmatch(text)
    if m:
        result = tools.save_memory(f"Krish ki content style: {m['s']}")
        return (f"Theek hai sir, aapki content style '{m['s']}' yaad rakh li." if not result.startswith("Error")
                else f"Sorry sir, {result}")
    if COPY_CMD.fullmatch(text):
        return f"Sorry sir, {tools.copy_last_content()}"
    m = EDITOR_CMD.fullmatch(text)
    if m:
        result = tools.open_editor(m["e"] or m["e2"])      # Install na ho to DirectReply "install nahi hai"
        return _tool_reply(result, hi, "Editor khol diya, sir.", "Opened the editor, sir.")

    raw = re.sub(r"^\s*(?:hey\s+)?(?:jarvis|jervis)[\s,]+", "", command or "", flags=re.I).strip()
    kw = _C_KW.search(raw)
    if not kw or not _C_VERB.search(raw) or _C_QUESTION.search(raw):
        return None
    topic = _content_topic(raw, kw)
    if len(topic.split()) < 1 or len(topic) < 2:
        return None                      # Topic nahi bataya - AI poochega
    result = tools.content_help(_C_KIND[kw[1].lower()], topic)
    return f"Sorry sir, {result}"        # Sahi chale to DirectReply uthta hai


# ============================================
# Read aloud / translator: "ye page padh ke sunao", "screen padh ke sunao", "clipboard padh do",
#   "https://... padh ke sunao". Sab fullmatch: "page kya hota hai", "padho" akela AI/dusre shortcut ke paas.
#   "Translator mode on: Hindi se English" main.py ka voice loop pakadta hai; yahan tak aaye (typed) to mana.
# ============================================
_R_VERB = (r"(?:padh ke sunao|padh kar sunao|padh ke suna do|padh ke suna de|padhke sunao|padh do|padh de|"
           r"padho|padhna|sunao|suna do|read aloud|read out|read out loud|read karo|read kar do)")
SCREEN_READ = re.compile(rf"(?:is |iss |ye |yeh |ye wala |is wala )?(?:page|screen|window|article|webpage|web page)"
                         rf"(?: ka text| ka content| ko| par ka text)? {_R_VERB}"
                         r"|read (?:this|the|my) (?:page|screen|article|window)(?: aloud| out loud| out)?"
                         r"|read (?:this|the|my) (?:page|screen|article|window)")
CLIPBOARD_READ = re.compile(rf"(?:is |iss |ye |yeh )?clipboard (?:ka |ke |wala |mein |me |ko )*(?:text |content )*"
                            rf"(?:ko )?{_R_VERB}|read (?:my |the )?clipboard(?: aloud| out loud| out)?")
URL_READ = re.compile(rf"\s*(?:jarvis[ ,]+)?(?:(?:read|padho|padh do|sunao)(?: aloud)?[: ]+(?P<u>(?:https?://|www\.)\S+)"
                      rf"|(?P<u2>(?:https?://|www\.)\S+) (?:ko |ka text )?{_R_VERB})\s*", re.I)


def _read_command(command, text):
    """Padh ke sunao commands (bina AI). Sahi chale to DirectReply uthta hai; yahan tak sirf error pe."""
    m = URL_READ.fullmatch(command or "")
    if m:
        return f"Sorry sir, {tools.read_webpage(m['u'] or m['u2'])}"
    if SCREEN_READ.fullmatch(text):
        return f"Sorry sir, {tools.read_screen()}"
    if CLIPBOARD_READ.fullmatch(text):
        return f"Sorry sir, {tools.read_clipboard()}"
    import translator
    if translator.parse_on(command) or translator.is_off(command):
        return "Translator mode sirf awaaz se chalta hai, sir. 'Jarvis, translator mode on: Hindi se English' boliye."
    return None


def _voice_profile_command(command):
    """"Meri awaaz bhool jao" (confirm ke saath, voice + typed dono) / typed "awaaz yaad karo" (mic chahiye)."""
    import speaker
    if speaker.is_forget_command(command):
        if speaker.profile() is None:
            return "Sir, abhi koi awaaz profile saved nahi hai."
        if not tools.confirm("Sir, pakka? Aapki awaaz ki profile mita doon? Phir JARVIS kisi ki bhi awaaz sunega."):
            return "Theek hai sir, awaaz profile waise hi rahegi."
        speaker.forget()
        return "Awaaz profile mita di, sir. Ab JARVIS sabki awaaz sunega. Dobara yaad karwane ke liye 'Jarvis meri awaaz yaad karo' boliye."
    if speaker.is_enroll_command(command):
        # Typed / HUD command: voice loop (jaagte hue) 10 vaakya wali enrollment chalayega. Voice se bola ho to
        # main.py ise pehle hi pakad leta hai. Kabhi AI / save_memory tak nahi jaata.
        speaker.enroll_requested.set()
        return "Theek hai sir, awaaz yaad karna shuru kar raha hoon. Main vaakya bolunga, aap dohraiye."
    return None


def _media_command(text, hi):
    """Media / volume-relative / brightness commands. Jawab (text) ya None (AI ke liye)."""
    # --- Brightness: "brightness 50 karo" (pehle, warna up/down se takra jayega) ---
    m = BRIGHTNESS_SET.fullmatch(text)
    if m:
        level = max(0, min(100, int(m["n"])))
        result = tools.brightness("set", level)
        return _tool_reply(result, hi, f"Screen brightness {level}% kar di, sir.",
                            f"Screen brightness set to {level}%, sir.")

    if BRIGHTNESS_UP.fullmatch(text):
        return _tool_reply(tools.brightness("up"), hi, "Screen ki roshni badha di, sir.",
                           "Screen brightness turned up, sir.")
    if BRIGHTNESS_DOWN.fullmatch(text):
        return _tool_reply(tools.brightness("down"), hi, "Screen ki roshni kam kar di, sir.",
                           "Screen brightness turned down, sir.")

    # --- Volume relative: "awaaz badhao" / "awaaz kam karo" ---
    if VOL_UP.fullmatch(text):
        return _tool_reply(tools.volume_change("up", 10), hi, "Awaaz badha di, sir.",
                           "Volume turned up, sir.")
    if VOL_DOWN.fullmatch(text):
        return _tool_reply(tools.volume_change("down", 10), hi, "Awaaz kam kar di, sir.",
                           "Volume turned down, sir.")

    # --- Media keys: pause/play, next, previous, stop ---
    if MEDIA_PLAY_PAUSE.fullmatch(text):
        return _tool_reply(tools.media_control("play_pause"), hi,
                           "Theek hai sir, gaana pause/chalu kar diya.",
                           "Done, sir - media play/pause.")
    if MEDIA_NEXT.fullmatch(text):
        return _tool_reply(tools.media_control("next"), hi, "Agla gaana chala diya, sir.",
                           "Skipped to the next track, sir.")
    if MEDIA_PREVIOUS.fullmatch(text):
        return _tool_reply(tools.media_control("previous"), hi, "Pichla gaana chala diya, sir.",
                           "Went back to the previous track, sir.")
    if MEDIA_STOP.fullmatch(text):
        return _tool_reply(tools.media_control("stop"), hi, "Gaana roka diya, sir.",
                           "Stopped playback, sir.")
    return None


def handle(command):
    """Simple command ho to khud chala ke jawab (text) do, warna None."""
    text = _clean(command)
    hi = _hinglish(text)

    # --- Awaaz profile ("meri awaaz yaad karo" / "bhool jao"): sabse pehle, memory/AI/save_memory tak kabhi nahi ---
    reply = _voice_profile_command(command)
    if reply:
        return reply

    # --- WhatsApp / calls (tools khud confirm + DRY_RUN + safety lock sambhalte hain) ---
    reply = _whatsapp_command(command, text)
    if reply:
        return reply

    # --- Memory commands (sabse pehle - correction/"Sahi hai?" ka jawab yahin) ---
    reply = _memory_command(command, text, hi)
    if reply:
        return reply

    # --- Memory: "mere baare mein kya jaante ho?" (bina AI, seedha memory.json se) ---
    if _asks_memory(text):
        import memory
        facts = memory.all_facts()
        if not facts:
            return ("Abhi mere paas aapke baare mein kuch save nahi hai, sir. "
                    "'Yaad rakhna ki...' bolke kuch bata dijiye.")
        return "Sir, mujhe yaad hai: " + " ".join(f if f.endswith(".") else f + "." for f in facts)

    reply = _read_command(command, text)          # Padh ke sunao (screen / page link / clipboard)
    if reply:
        return reply

    # --- Morning briefing (template, bina AI; DirectReply seedha jawab) ---
    if BRIEFING_CMD.fullmatch(text):
        return f"Sorry sir, briefing nahi bana paya. {tools.morning_briefing()}"

    # --- Screen: "screen pe kya hai" -> seedha look_at_screen (jawab DirectReply se aata hai) ---
    if SCREEN_ASK.fullmatch(text):
        result = tools.look_at_screen(command)
        return f"Sorry sir, screen nahi dekh paya. {result}"   # Yahan sirf error pe pahunchte hain

    # --- Time / date ---
    is_time, is_date = _is(text, TIME_KEYS), _is(text, DATE_KEYS)
    if is_time or is_date:
        info = tools.get_time_date()        # "Time: 09:41 PM, Date: 25 September 2026, Day: Friday"
        parts = dict(p.split(": ", 1) for p in info.split(", "))
        if is_time:
            return f"Sir, abhi {parts['Time']} ho rahe hain." if hi else f"It's {parts['Time']}, sir."
        return (f"Aaj {parts['Day']}, {parts['Date']} hai, sir." if hi
                else f"Today is {parts['Day']}, {parts['Date']}, sir.")

    # --- Battery / CPU / RAM ---
    # ("kaun" wala sawaal - jaise "ram kaun hai" - system info nahi, AI ke liye hai)
    if _is(text, SYSTEM_KEYS) and not set(text.split()) & {"kaun", "कौन"}:
        info = tools.system_info()
        # Sirf battery poochhi hai to sirf battery batao
        m = re.search(r"Battery: (\d+)% \((\w[\w ]*)\)", info)
        if m and set(text.split()) & {"battery", "बैटरी", "charge", "charging"}:
            charging = m[2] == "charging"
            if hi:
                return f"Sir, battery {m[1]}% hai, {'charge ho rahi hai' if charging else 'charging pe nahi hai'}."
            return f"Battery is at {m[1]}%, {'charging' if charging else 'not charging'}, sir."
        return info

    # --- PC shutdown / restart (confirmation tool ke andar hai) ---
    # Tool apna jawab khud seedha deta hai (DirectReply) - cancel, test mode, ya
    # "10 second mein band". Yahan tak sirf error aane pe pahunchte hain.
    if PC_SHUTDOWN.fullmatch(text) or PC_RESTART.fullmatch(text):
        result = tools.restart_pc() if PC_RESTART.fullmatch(text) else tools.shutdown_pc()
        return f"Sorry sir, nahi ho paya. {result}"

    # --- Weather (Open-Meteo, bina AI) ---
    m = WEATHER_HI.fullmatch(text) or WEATHER_EN.fullmatch(text)
    if m:
        # "aaj delhi" -> "delhi". Kal/tomorrow ka mausam ye tool nahi deta -> AI ko do
        city = re.sub(r"^(aaj|abhi|today|aaj ka|aaj ki)\s+", "", m["city"]).strip()
        if city and not set(city.split()) & {"kal", "tomorrow", "aaj", "abhi", "yahan", "here"}:
            result = tools.get_weather(city)
            w = tools.last_weather
            if result.startswith(("Error", "Could not")) or not w:
                return f"Sorry sir, {city} ka mausam nahi mil paya."
            if hi:
                return (f"Sir, {w['city']} mein abhi {w['temp']} degree hai, {w['desc']}. "
                        f"Aaj {w['min']} se {w['max']} degree, baarish ka chance {w['rain']} percent.")
            return (f"In {w['city']} it's {w['temp']} degrees, {w['desc']}. "
                    f"Today {w['min']} to {w['max']} degrees, {w['rain']} percent chance of rain, sir.")

    # --- Volume ---
    m = VOLUME.fullmatch(text)
    if m:
        result = tools.set_volume(int(m["n"]))
        if result.startswith("Error"):
            return f"Sorry sir, volume nahi badal paya. {result}"
        level = min(100, int(m["n"]))
        return f"Volume {level}% kar diya, sir." if hi else f"Volume set to {level}%, sir."
    if UNMUTE.fullmatch(text):              # "unmute" pehle check, warna "mute" pakad leta
        tools.set_mute(False)
        return "Awaaz chalu kar di, sir." if hi else "Unmuted, sir."
    if MUTE.fullmatch(text):
        tools.set_mute(True)
        return "Mute kar diya, sir." if hi else "Muted, sir."

    # --- Media keys / volume relative / brightness (app/website se PEHLE, warna "chalu karo"
    #     wali commands galat jagah chali jaati hain) ---
    reply = _dev_command(command, text, hi)        # Dev helper: clipboard samjhao, git status/log
    if reply:
        return reply

    reply = _content_command(command, text, hi)    # Content pack: caption, script, copy, editors
    if reply:
        return reply

    reply = _notes_command(command, text, hi)      # Notes: text asli command se (lowercase nahi)
    if reply:
        return reply

    reply = _tasks_command(command, text, hi)      # Reminders / tasks
    if reply:
        return reply

    reply = _files_command(text, hi)      # Files pehle: "downloads mein pdf kholo" open-app se na takraye
    if reply:
        return reply

    reply = _media_command(text, hi)
    if reply:
        return reply

    # --- App / website kholna ---
    m = OPEN_EN.fullmatch(text) or OPEN_HI.fullmatch(text)
    if m:
        name = m["name"].strip()
        result = _open(name)
        if result is not None:
            if result.startswith("Sorry"):      # Kholne mein error aaya
                return result
            return f"{name.title()} khol raha hoon, sir." if hi else f"Opening {name.title()}, sir."

    return None      # Simple command nahi hai -> AI (Gemini/Groq) sambhalega
