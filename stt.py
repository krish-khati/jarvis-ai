# ============================================
# stt.py - Speech-to-text (awaaz -> text), 3 engines with fallback
#   1. Gemini transcribe  (gemini-3.5-transcribe, custom vocabulary)
#   2. Groq Whisper       (whisper-large-v3-turbo, vocabulary as prompt)
#   3. Google             (speech_recognition, purana tareeqa)
#   Order .env ke STT_ORDER se aata hai (benchmark ke baad sabse fast + sahi pehle).
#   Har call count hoti hai (stt_usage.json, roz reset); limit ya error pe agla engine.
# ============================================

import datetime      # Roz ka count reset karne ke liye
import io            # Audio ko file ki jagah memory mein rakhna
import json          # Usage file
import os            # .env / paths
import re            # Vocabulary words saaf karna
import time          # Latency + cooldown
import wave          # Raw audio -> wav bytes

import speech_recognition as sr
from dotenv import load_dotenv

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))
VOCAB_FILE = os.path.join(HERE, "vocab.txt")
USAGE_FILE = os.path.join(HERE, "stt_usage.json")     # gitignored

# --- Settings (.env se; yahan sirf default) ---
import logging as _logging
for _n in ("google_genai", "google_genai.models", "google_genai.types"):
    _logging.getLogger(_n).setLevel(_logging.ERROR)     # AFC warning chup

STT_ORDER = [e.strip() for e in os.getenv("STT_ORDER", "groq,google,gemini").split(",") if e.strip()]
GEMINI_STT_MODEL = os.getenv("GEMINI_STT_MODEL", "gemini-3.5-transcribe")
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
# Roz ki call limit (0 = koi limit nahi). Asli limit se thodi kam rakhi hai; 429 aaye to bhi switch hota hai
LIMITS = {
    "gemini": int(os.getenv("STT_GEMINI_DAILY_LIMIT", "100")),
    "groq": int(os.getenv("STT_GROQ_DAILY_LIMIT", "1500")),
    "google": int(os.getenv("STT_GOOGLE_DAILY_LIMIT", "0")),
}
# Per-minute limit (naapa hua: Gemini transcribe free tier ~4-5 calls/minute). 0 = koi nahi
RPM = {
    "gemini": int(os.getenv("STT_GEMINI_RPM", "4")),
    "groq": int(os.getenv("STT_GROQ_RPM", "18")),      # Groq whisper free: 20/min
    "google": 0,
}
# Engine fail ho to kitni der skip (429 = limit, baaki = network/503 jaisa)
REST_429 = 30              # Per-minute limit: retryDelay na mile to 30s
REST_429_DAILY = 30 * 60   # Daily limit ("PerDay") ka error
REST_OTHER = 60
MAX_VOCAB_IN_PROMPT = 60      # Prompt lamba na ho (latency + Whisper ki 224 token limit)

_down_until = {}              # engine -> time jab tak skip
_recent = {}                  # engine -> pichhle 60s ki call ka time (per-minute limiter)
_gemini = None
_groq = None
last_engine = None            # Aakhri baar kisne suna
last_seconds = 0.0            # Aur kitni der lagi


# ============================================
# Vocabulary: vocab.txt (aap edit karo) + memory ke naam
# ============================================
def _file_words():
    """vocab.txt: har line ek word/phrase, '#' se shuru line comment."""
    try:
        with open(VOCAB_FILE, encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError:
        return []


def _memory_words():
    """Memory ke facts se naam jaise shabd (Capital ya letters+digits wale). Sirf RAM mein, file mein nahi likhte."""
    try:
        import memory
        facts = memory.all_facts()
    except Exception:
        return []
    out = []
    for fact in facts:
        for w in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", fact):
            if w[0].isupper() or any(c.isdigit() for c in w):
                out.append(w)
    return out


def vocabulary():
    """Sab important words, duplicate hata ke (case ignore)."""
    seen, out = set(), []
    for w in _file_words() + _memory_words():
        if w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out[:MAX_VOCAB_IN_PROMPT]


# ============================================
# Usage counting (roz reset)
# ============================================
def _load_usage():
    today = datetime.date.today().isoformat()
    try:
        with open(USAGE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") == today:
            return data
    except (OSError, ValueError):
        pass
    return {"date": today, "counts": {}}


def usage(engine):
    return _load_usage()["counts"].get(engine, 0)


def _count(engine):
    data = _load_usage()
    data["counts"][engine] = data["counts"].get(engine, 0) + 1
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def _usable(engine):
    """Engine abhi try karne layak hai? (daily + per-minute limit baaki hai aur aaram pe nahi)"""
    now = time.time()
    if now < _down_until.get(engine, 0):
        return False
    limit = LIMITS.get(engine, 0)
    if limit and usage(engine) >= limit:
        return False
    rpm = RPM.get(engine, 0)
    calls = _recent.setdefault(engine, [])
    calls[:] = [t for t in calls if now - t < 60]
    return not (rpm and len(calls) >= rpm)


def _rest_seconds(e):
    """429 ke baad kitni der us engine ko chhodo (error mein retryDelay / PerDay dekh ke)."""
    text = str(e)
    if "PerDay" in text:
        return REST_429_DAILY
    m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+)", text)
    return max(int(m.group(1)) + 1, 5) if m else REST_429


# ============================================
# Engines
# ============================================
def to_wav(audio):
    """sr.AudioData -> 16kHz mono wav bytes."""
    return audio.get_wav_data(convert_rate=16000, convert_width=2)


def _clean(text):
    """Model ke extra shabd hatao (quotes, 'Transcript:' jaisa)."""
    text = (text or "").strip().strip('"').strip()
    text = re.sub(r"^(transcript|transcription)\s*[:\-]\s*", "", text, flags=re.I)
    return text.strip()


def _gemini_engine(audio, wav):
    global _gemini
    if _gemini is None:
        from google import genai
        _gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    from google.genai import types
    # Transcribe model text prompt nahi samajhta - vocabulary uske apne config mein jaati hai
    # (auto language: Hinglish Roman letters mein hi aata hai)
    r = _gemini.models.generate_content(
        model=GEMINI_STT_MODEL,
        contents=[types.Part.from_bytes(data=wav, mime_type="audio/wav")],
        config=types.GenerateContentConfig(
            audio_transcription_config=types.AudioTranscriptionConfig(custom_vocabulary=vocabulary())),
    )
    parts = r.candidates[0].content.parts if r.candidates and r.candidates[0].content else []
    return _clean(" ".join(p.audio_transcription.text for p in parts
                           if getattr(p, "audio_transcription", None) and p.audio_transcription.text))


def _groq_engine(audio, wav):
    global _groq
    if _groq is None:
        from groq import Groq
        _groq = Groq(api_key=os.getenv("GROQ_API_KEY"), max_retries=0, timeout=4)   # Chupke retry nahi: fail ho to agla engine
    words = vocabulary()
    # Whisper "prompt" = pichla context: jaisa text yahan hoga, output ka style waisa hi aayega.
    # Isliye Roman Hinglish ke example sentences (vocab.txt ke words ke saath) + shabdon ki list.
    examples = " ".join(f"{w} kholo." if i % 2 == 0 else f"{w} ko message bhejo." for i, w in enumerate(words[:8]))
    prompt = (f"Roman Hinglish only, English letters, never Devanagari. {examples} "
              f"Chrome mein GitHub kholo. VS Code open karo. Papa ko message bhejo ki main late aaunga. "
              f"Words: {', '.join(words)}.")
    r = _groq.audio.transcriptions.create(
        file=("audio.wav", wav), model=GROQ_STT_MODEL, prompt=prompt[:850],
        response_format="text", temperature=0, language="en")
    text = _clean(r if isinstance(r, str) else getattr(r, "text", ""))
    if re.search(r"[ऀ-ॿ]", text):     # Devanagari aaya -> ye engine fail, agla engine sunega
        raise ValueError("Groq ne Devanagari diya")
    return text


_recognizer = sr.Recognizer()


def _google_engine(audio, wav):
    for language in ("en-IN", "hi-IN"):
        try:
            return _clean(_recognizer.recognize_google(audio, language=language))
        except sr.UnknownValueError:
            continue
    return ""


ENGINES = {"gemini": _gemini_engine, "groq": _groq_engine, "google": _google_engine}


# ============================================
# Main entry: fallback chain
# ============================================
def transcribe(audio, order=None):
    """audio (sr.AudioData) -> (text, engine). Kuch na suna to (None, engine ya None).
    Engine error/limit pe agla engine; sab fail hon to (None, None)."""
    global last_engine, last_seconds
    wav = to_wav(audio)
    for name in (order or STT_ORDER):
        if name not in ENGINES or not _usable(name):
            continue
        started = time.time()
        _count(name)
        _recent.setdefault(name, []).append(started)
        try:
            text = ENGINES[name](audio, wav)
        except Exception as e:
            code = getattr(e, "code", None) or getattr(e, "status_code", None)
            rest = _rest_seconds(e) if (code == 429 or "429" in str(e)[:40]) else REST_OTHER
            _down_until[name] = time.time() + rest
            print(f"  (STT {name} error {code or ''}: {str(e)[:100]}) -> agla engine")
            continue
        last_engine, last_seconds = name, time.time() - started
        return (text or None), name
    return None, None
