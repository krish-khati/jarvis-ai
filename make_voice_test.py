# make_voice_test.py - Hinglish me awaaz compare karne ke liye test files banata hai
#
#   python make_voice_test.py
#
# 5 Hinglish sentences x 3 awaazein -> voice_test/ folder (gitignore hai):
#   1_eleven_flash25.mp3    ElevenLabs flash (current, tez + sasta)
#   2_eleven_multiling.mp3  ElevenLabs multilingual v2 (sunaawat khoobsurat, mehngi)
#   3_edge_hi_madhur.mp3    edge-tts hi-IN-MadhurNeural (free, poori Hindi)
#   (+ 4_eleven_v3.mp3      ElevenLabs v3 - naya model, bonus ke liye)
#
# Sunein aur bataiye kaunsi pasand aayi - main .env mein ELEVENLABS_MODEL usi par
# set kar dunga. Voice ID bhi badalni ho to .env ELEVENLABS_VOICE_ID badal do.

import asyncio
import os
import sys

import edge_tts
import httpx
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "voice_test")
load_dotenv(os.path.join(ROOT, ".env"))

KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
EL_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_flash_v2_5")
EDGE_VOICE = "hi-IN-MadhurNeural"
V3 = "eleven_v3"      # bonus: naya model, Hinglish ke liye behtar hota hai

# 5 lines - chhoti, everyday, numbers/saat bhi (wahi test hai jo awaaz ki quality dikhata hai)
LINES = [
    "Sir, aaj ka mausam kaisa hai?",
    "Theek hai sir, main aapke liye Spotify chala raha hoon.",
    "Sir, 3 naye WhatsApp messages aaye hain, ek Rahul se hai.",
    "Kya aap chahte hain ke main yeh message bhej doon?",
    "Ji sir, kaam ho gaya, battery ab 80 percent par hai.",
]


def eleven(text, model, path):
    """ElevenLabs se mp3. Key nahi ya model na chale to False."""
    if not KEY:
        return False
    try:
        with httpx.Client(timeout=90) as c:
            r = c.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
                       headers={"xi-api-key": KEY, "Content-Type": "application/json"},
                       json={"text": text, "model_id": model,
                             "output_format": "mp3_44100_128"})
        if r.status_code != 200:
            print(f"  ! {model}: HTTP {r.status_code} {r.text[:120]}")
            return False
        with open(path, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print(f"  ! {model}: {str(e)[:120]}")
        return False


async def edge(text, path):
    """edge-tts se mp3 (free, poori Hindi)."""
    try:
        await edge_tts.Communicate(text, EDGE_VOICE).save(path)
        return True
    except Exception as e:
        print(f"  ! edge-tts: {str(e)[:120]}")
        return False


def size_kb(p):
    return f"{os.path.getsize(p)/1024:.0f} KB" if os.path.exists(p) else "-"


def main():
    os.makedirs(OUT, exist_ok=True)
    print(f"Folder: {OUT}")
    print(f"Voice ID: {VOICE_ID}   (.env ELEVENLABS_VOICE_ID)")
    print(f"Model (.env ELEVENLABS_MODEL): {EL_MODEL}")
    print(f"edge-tts: {EDGE_VOICE}\n")

    jobs = [("1_eleven_flash25", lambda t, p: eleven(t, EL_MODEL, p)),
            ("2_eleven_multiling", lambda t, p: eleven(t, "eleven_multilingual_v2", p)),
            ("3_edge_hi_madhur", lambda t, p: asyncio.run(edge(t, p))),
            ("4_eleven_v3_bonus", lambda t, p: eleven(t, V3, p))]

    ok = {}
    for prefix, make in jobs:
        good = 0
        for i, line in enumerate(LINES, 1):
            p = os.path.join(OUT, f"{prefix}_{i}.mp3")
            if make(line, p) and os.path.getsize(p) > 500:
                good += 1
            print(f"  {prefix}_{i}.mp3  {size_kb(p):>8}  {line[:44]}")
        ok[prefix] = good
        print(f"  -> {good}/{len(LINES)} bani\n")

    print("=" * 58)
    for prefix, good in ok.items():
        print(f"  {prefix:24} {good}/{len(LINES)}")
    print("=" * 58)
    if ok.get("1_eleven_flash25") == len(LINES):
        print(f"\nPasand aane wale model ka naam .env mein ELEVENLABS_MODEL mein daal do "
              f"(abhi: {EL_MODEL})")
    else:
        print("\nElevenLabs nahi chala - khaali folder dekh lo, edge-tts wali files to banti hain.")
    return 0 if all(v == len(LINES) for v in ok.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
