# ============================================
# contacts.py - naam -> number (contacts.json se)
#   "mummy", "mom", "maa" -> sab ek hi contact (aliases + fuzzy match)
#   contacts.json GitHub pe NAHI jaati (.gitignore). Format: contacts.example.json dekho.
#   Number kabhi khud nahi banate - contact na mile to None.
# ============================================

import difflib     # Milte-julte naam dhoondhne ke liye ("rahool" -> "rahul")
import json
import os
import re

CONTACTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "contacts.json")


def _load():
    """contacts.json padho: {"Mom": {"number": "+91...", "aliases": ["mummy", "maa"]}, ...}"""
    try:
        with open(CONTACTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _norm(text):
    """Chhote akshar, faltu words hatao: "Mummy ji ko" -> "mummy" """
    text = re.sub(r"[^\w\s]", " ", str(text).lower())
    words = [w for w in text.split() if w not in {"ji", "ko", "ka", "ki", "ke", "se", "mere", "meri", "mera", "my", "the"}]
    return " ".join(words)


def find(name):
    """Naam se contact dhoondho.
    Return: ("found", naam, number) / ("ambiguous", [naam, naam], None) / ("missing", None, None)"""
    contacts = _load()
    if not contacts:
        return "missing", None, None
    q = _norm(name)
    if not q:
        return "missing", None, None

    # Har contact ke saare naam (asli naam + aliases)
    names = {}
    for real, info in contacts.items():
        for alias in [real] + list(info.get("aliases", [])):
            names[_norm(alias)] = real

    # 1. Seedha match
    if q in names:
        real = names[q]
        return "found", real, contacts[real]["number"]
    # 2. Fuzzy match ("rahool" -> "rahul", "mumma" -> "mummy")
    close = difflib.get_close_matches(q, names.keys(), n=3, cutoff=0.75)
    matches = sorted({names[c] for c in close})
    if len(matches) == 1:
        return "found", matches[0], contacts[matches[0]]["number"]
    if len(matches) > 1:
        return "ambiguous", matches, None
    return "missing", None, None


def digits(number):
    """"+91 98765-43210" -> "919876543210" (WhatsApp link ke liye sirf ank)"""
    return re.sub(r"\D", "", str(number))


def mask(number):
    """Terminal/UI mein pura number kabhi nahi - sirf aakhri 4 ank: "******3210" """
    d = digits(number)
    return "*" * max(0, len(d) - 4) + d[-4:] if d else "????"


def exists():
    return os.path.exists(CONTACTS_FILE)
