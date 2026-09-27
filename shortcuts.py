# ============================================
# shortcuts.py - Simple commands bina AI ke (Gemini/Groq ki requests bachti hain)
#   time/date, battery/system, volume/mute, app ya website kholna,
#   PC shutdown/restart (confirmation ke saath)
#
# Har pattern POORE command se match hota hai (sirf ek word nahi), taaki
# "match kis time shuru hoga" jaisa sawaal galti se "time" shortcut na bane -
# wo AI ke paas jaayega. Match na ho to handle() None deta hai -> AI sambhalega.
# ============================================

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
    r"|((meri )?screen dekho)|(what'?s on (my |the )?screen)|(look at (my |the )?screen)")


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


def handle(command):
    """Simple command ho to khud chala ke jawab (text) do, warna None."""
    text = _clean(command)
    hi = _hinglish(text)

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
