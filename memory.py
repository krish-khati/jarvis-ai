# ============================================
# memory.py - JARVIS ki long-term memory (lambe samay tak yaad)
#   Krish ki important baatein (birthday, pasand, dost ke naam...) memory.json
#   mein save hoti hain. Program band karke dobara chalao, tab bhi yaad rehti hain.
#   brain.py har AI request ke system prompt mein ye baatein bhejta hai.
# ============================================

import datetime    # Kab save hua, ye likhne ke liye
import json        # memory.json padhne/likhne ke liye
import os          # File ka rasta
import re          # Words todne ke liye (delete mein match dhoondhna)

# memory.json isi folder mein (git mein nahi jaati - .gitignore dekho)
MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.json")

# Is session mein aakhri baar jo baat save/update hui - "galat hai", "iske peeche 972 bhi
# hai" jaisi correction ISI pe lagti hai (nayi memory nahi banti)
last_fact = None
# Read-back ke baad "Sahi hai?" poocha hai - agla "haan"/"nahi" isi ke liye hai
awaiting_check = False
# JARVIS ka PICHLA jawab memory ke baare mein tha? "galat hai" jaisi correction tabhi
# memory pe lagti hai (warna weather ke jawab pe "galat hai" se memory mit jaati).
# brain.ask() har jawab ke baad ise set karta hai.
recent = False
touched = False
# Aakhri badlaav: ("saved", None, nayi) ya ("updated", purani, nayi) - "galat hai" isse UNDO karta hai
last_change = None      # Is jawab mein memory chhui gayi? (brain.ask padhta hai)


def _load():
    """memory.json padho. File na ho ya kharab ho to khaali list."""
    try:
        with open(MEMORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as e:
        # File haath se edit karte waqt JSON toot gaya (comma/bracket chhoot gaya).
        # Khaali maan ke overwrite karte to SAARI memory chali jaati - isliye pehle
        # tooti file ka backup bana do, taaki aap VS Code mein theek kar sako.
        backup = MEMORY_FILE + ".broken"
        os.replace(MEMORY_FILE, backup)
        print(f"  [MEMORY] memory.json kharab hai ({e}). Backup: {backup} - "
              f"use theek karke wapas memory.json naam do.")
        return []


def _save(items):
    """Poori list memory.json mein likho (Hindi bhi sahi save ho - ensure_ascii=False)."""
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def all_facts():
    """Saari yaad rakhi baatein (sirf text) ki list."""
    return [item["fact"] for item in _load()]


def add(fact):
    """Nayi baat jodo, ya milti-julti purani baat ko UPDATE karo.
    Return: ("same", purani) / ("updated", purani) / ("saved", None)

    Update kab: purani aur nayi baat mein 2+ khaas words same hon (jaise
    "GitHub username krrish" -> "GitHub username krrish972": dono mein
    "github" + "username"). Isse sudhaar karne pe duplicate entry nahi banti."""
    global last_fact, touched
    touched = True
    fact = fact.strip()
    items = _load()
    new_words = _words(fact)
    for i in items:
        if _words(i["fact"]) == new_words:
            last_fact = i["fact"]
            return "same", i["fact"]
    for i in items:
        if len(_words(i["fact"]) & new_words) >= 2:
            old = i["fact"]
            i["fact"], i["saved"] = fact, datetime.date.today().isoformat()
            _save(items)
            last_fact = fact
            _set_change("updated", old, fact)
            return "updated", old
    items.append({"fact": fact, "saved": datetime.date.today().isoformat()})
    _save(items)
    last_fact = fact
    _set_change("saved", None, fact)
    return "saved", None


def _set_change(kind, old, new):
    global last_change
    last_change = (kind, old, new)


def undo_last():
    """"Galat hai" - aakhri badlaav palto:
      naya save hua tha  -> hata do
      update hua tha     -> purani value wapas lao (sahi wali kho na jaaye)
    Return: ("removed", baat) / ("restored", purani) / None"""
    global last_fact, last_change, touched
    touched = True
    if not last_change:
        return None
    kind, old, new = last_change
    items = _load()
    for i in items:
        if i["fact"] == new:
            if kind == "updated" and old:
                i["fact"] = old
                _save(items)
                last_fact, last_change = old, None
                return "restored", old
            items.remove(i)
            _save(items)
            last_fact, last_change = None, None
            return "removed", new
    return None


def remove(query):
    """query se sabse zyada milti-julti baat(ein) hatao. Hataayi gayi baatein return.
    Jaise query "birthday" -> "Krish ka birthday 9 June ko hai" hat jaayegi."""
    global touched
    touched = True
    items = _load()
    q = _words(query)
    if not q:
        return []
    # Har baat ka score = kitne words query se milte hain
    scored = [(len(q & _words(i["fact"])), i) for i in items]
    best = max((s for s, _ in scored), default=0)
    if best == 0:
        return []
    removed = [i["fact"] for s, i in scored if s == best]
    _save([i for s, i in scored if s != best])
    return removed


def numbered():
    """"Memory dikhao" ke liye: [(1, "baat"), (2, "baat"), ...]"""
    return list(enumerate(all_facts(), start=1))


def remove_number(n):
    """"Memory 3 hatao" - number n wali baat hatao. Hataayi baat return (ya None)."""
    global last_fact, touched
    touched = True
    items = _load()
    if not 1 <= n <= len(items):
        return None
    removed = items.pop(n - 1)["fact"]
    _save(items)
    if removed == last_fact:
        last_fact = None
    return removed


def replace_last(new_fact):
    """Aakhri save hui baat ko new_fact se badlo (correction). (purani, nayi) return."""
    global last_fact, touched
    touched = True
    items = _load()
    for i in items:
        if i["fact"] == last_fact:
            old = i["fact"]
            i["fact"], i["saved"] = new_fact, datetime.date.today().isoformat()
            _save(items)
            last_fact = new_fact
            _set_change("updated", old, new_fact)
            return old, new_fact
    return None


def delete_last():
    """"Galat hai" - aakhri save hui baat hatao. Hataayi baat return (ya None)."""
    global last_fact, touched
    touched = True
    items = _load()
    kept = [i for i in items if i["fact"] != last_fact]
    if len(kept) == len(items):
        return None
    _save(kept)
    removed, last_fact = last_fact, None
    return removed


def append_to_last(extra):
    """"Iske peeche 972 bhi hai" - aakhri baat ke username/ID ke peeche extra jodo.
    "Krish ka GitHub username krrish hai" + "972" -> "... krrish972 hai" """
    if not last_fact:
        return None
    tokens = last_fact.split()
    # Peeche se pehla "value jaisa" word dhoondho (hai/ko/ka jaise words chhod ke)
    for idx in range(len(tokens) - 1, -1, -1):
        if tokens[idx].lower().strip(".") not in _STOP | {"hai.", "=", ":"}:
            tokens[idx] = tokens[idx].rstrip(".") + extra
            return replace_last(" ".join(tokens))
    return None


# Username/email/ID jaise words - inki spelling bol ke sunate hain.
# (1) letters+numbers mile ("krrish972"), @ ya _ wale, "=" ke baad wale, ya
# (2) baat mein username/email/id/password jaisa word ho to uski value ("krrish")
ID_KEYWORDS = {"username", "user", "email", "mail", "id", "handle", "password", "account",
               "number", "phone", "mobile", "upi", "pin", "code"}


def ids_in(fact):
    after_eq = fact.split("=", 1)[1].split() if "=" in fact else []
    tokens = [t.strip(".,") for t in fact.replace("=", " = ").split()]
    found = []
    for t in tokens:
        has_letter, has_digit = re.search(r"[A-Za-z]", t), re.search(r"\d", t)
        if (t in after_eq or (has_letter and has_digit) or "@" in t or "_" in t) and len(t) >= 3:
            found.append(t)
    if not found and {t.lower() for t in tokens} & ID_KEYWORDS:
        # Keyword ke baad wala pehla "value" word ("GitHub username krrish hai" -> "krrish")
        seen_key = False
        for t in tokens:
            if t.lower() in ID_KEYWORDS:
                seen_key = True
            elif seen_key and t.lower() not in _STOP | ID_KEYWORDS and len(t) >= 2:
                found.append(t)
                break
    return found


_SPELL_WORDS = {".": "dot", "@": "at", "_": "underscore", "-": "dash"}


def spell(word):
    """"krrish972" -> "K-R-R-I-S-H-9-7-2", "a.b@x" -> "A-dot-B-at-X" (bol ke sunane ke liye)"""
    return "-".join(_SPELL_WORDS.get(ch, ch.upper()) for ch in word if ch.isalnum() or ch in _SPELL_WORDS)


def readback(fact, action_hi, action_en, hi=True):
    """Save ke baad bolne wali line: exact baat + ID ki spelling + "Sahi hai?"
    Jaise: "Yaad rakh liya: aapka GitHub username krrish972 hai. Spelling: K-R-R-I-S-H-9-7-2. Sahi hai?" """
    global awaiting_check, touched
    touched = True
    shown = you(fact)
    ids = ids_in(fact)
    line = f"{action_hi if hi else action_en}: {shown}."
    if ids:
        line += (" Spelling: " if hi else " Spelled: ") + ", ".join(spell(i) for i in ids) + "."
        line += " Sahi hai?" if hi else " Is that right?"
        awaiting_check = True
    return line


def you(fact):
    """Bolne ke liye: "Krish ka GitHub..." -> "aapka GitHub..." """
    for a, b in (("Krish ka ", "aapka "), ("Krish ki ", "aapki "), ("Krish ke ", "aapke "),
                 ("Krish ko ", "aapko "), ("Krish's ", "your ")):
        fact = fact.replace(a, b)
    return fact.rstrip(".")


def clear():
    """Saari memory mitao. Kitni baatein thi, wo return."""
    count = len(_load())
    _save([])
    return count


# Chhote/common words match mein nahi gine jaate ("ka", "hai", "the"...)
_STOP = {"ka", "ki", "ke", "hai", "hain", "ko", "se", "mein", "me", "aur", "ye", "wo", "is",
         "the", "a", "an", "is", "of", "to", "and", "my", "mera", "meri", "mere", "krish",
         "wali", "wala", "baat", "about", "that", "jo", "bhi"}


def _words(text):
    return set(re.findall(r"[^\s.,!?।'\"=:]+", text.lower())) - _STOP
