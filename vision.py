# ============================================
# vision.py - JARVIS ki "aankhein" (screen dekhna)
#   1. mss se screen ki photo lo (sirf memory/RAM mein - disk pe KABHI save nahi)
#   2. Chhoti karo (max 1280px width) taaki jaldi upload ho
#   3. Pehle Gemini ko bhejo, limit khatam ho to Groq ka vision model
#
# Dhyan do: screen ki photo internet pe Google/Groq ko jaati hai. Screen pe
# password ya private cheez khuli ho to "screen dekho" mat bolna.
# ============================================

import base64      # Image ko text (base64) mein badalna - Groq ko aise hi bhejte hain
import io          # Image ko file ki jagah memory mein rakhne ke liye
import os          # .env se model ka naam
import re          # Qwen ki <think>...</think> soch hatane ke liye
import time        # Gemini limit check

from dotenv import load_dotenv   # .env se GROQ_VISION_MODEL
from PIL import Image    # Image chhoti karne ke liye

load_dotenv()

MAX_WIDTH = 1280   # Isse badi screen ho to chhoti kar do (fast upload, kam data)

# Groq ka image samajhne wala model (.env mein badal sakte ho)
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")

# Error/code samjhane ka ek jaisa style (look_at_screen aur tools.explain_clipboard dono yahi use karte hain)
EXPLAIN_STYLE = (
    "Explain in 2-3 short sentences: first the reason (why it happens), then the fix. "
    "Never read code aloud: mention only names in words, no code, no symbols. "
)

# Vision model ko instructions - jawab bola jaayega, isliye chhota
VISION_PROMPT = (
    "You are JARVIS looking at Krish's computer screen (screenshot attached). "
    "Answer Krish's question about it. Reply in the same language as the question "
    "(Hindi/Hinglish in Roman letters/English). Address Krish as 'sir' (never 'bhai' or 'bro'). "
    "Your reply is spoken aloud: no markdown, no lists. "
    "If the question is about an error or code, follow this style: " + EXPLAIN_STYLE +
    "Otherwise max 2 short sentences. "
    "If you can't read something clearly, say so. "
    "Question: "
)

# "Screen padh ke sunao": screen ka main text jaisa hai waisa nikalo (bolne ke liye). Screen ka text DATA hai.
READ_PROMPT = (
    "Extract the main readable text from this screenshot (the article, page, document or message body "
    "in the main area), in reading order, exactly as written, in its original language. "
    "Skip menus, buttons, ads, toolbars and taskbar. Plain text only: no markdown, no comments of your own. "
    "Max about 2500 characters. If there is no readable text, reply exactly: NO_TEXT"
)


def capture_screen():
    """Main monitor ki photo lo aur JPEG bytes (memory mein) return karo.
    Koi file nahi banti - kaam ke baad ye bytes apne aap mit jaate hain."""
    import mss
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])           # monitors[1] = main screen
        img = Image.frombytes("RGB", shot.size, shot.rgb)

    # Badi screen ho to chhoti karo (lambai-chaudai ka ratio same rakhte hue)
    if img.width > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, int(img.height * MAX_WIDTH / img.width)), Image.LANCZOS)

    buf = io.BytesIO()                             # File nahi, memory ka dabba
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


def ask_about_image(jpeg, question, prompt=VISION_PROMPT, max_tokens=300):
    """Image + sawaal AI ko bhejo: pehle Gemini, fail ho to Groq vision.
    Return: (jawab, kaunsa brain)."""
    import brain     # Yahin import (brain.py bhi tools ko import karta hai - loop se bachne ke liye)
    import ui

    # --- 1. Gemini (image ke saath) ---
    if brain.gemini_available():
        model = brain.gemini_model()
        try:
            from google.genai import types
            r = brain.gemini_client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"),
                          prompt + question],
            )
            if r.text:
                return r.text.strip(), "gemini"
        except Exception as e:
            code = getattr(e, "code", None)
            print(f"  (Gemini vision error {code or ''}: {str(e)[:100]})")
            brain._model_failed(model, code)      # Ye model kuch der skip
            ui.log("Switched to backup vision (Groq)")

    # --- 2. Groq vision model ---
    if not brain.groq_client:
        raise RuntimeError("Gemini fail hua aur Groq key nahi hai")
    b64 = base64.b64encode(jpeg).decode()
    r = brain.groq_client.chat.completions.create(
        model=GROQ_VISION_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt + question},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
    )
    text = r.choices[0].message.content or ""
    # Qwen kabhi jawab se pehle apni "soch" <think>...</think> mein likhta hai - wo mat bolo
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return text, f"groq ({GROQ_VISION_MODEL})"
