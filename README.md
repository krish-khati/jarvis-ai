# J.A.R.V.I.S

Krish ka personal AI assistant: Hinglish mein bolo ya type karo, JARVIS sunta hai, sochta hai, PC chalata hai aur British awaaz mein jawab deta hai. Full-screen sci-fi HUD aur system tray ke saath.

## Kya-kya karta hai

- **Wake word (offline):** "Hey Jarvis" / "Jarvis wake up" pe jaagta hai. Vosk se chalta hai, internet nahi chahiye, CPU kam lagta hai.
- **Sunna:** Google speech (en-IN, na samjhe to hi-IN), aur spell kiye naam jodta hai ("k r r i s h 9 7 2" → `krrish972`).
- **Dimaag:** Gemini main brain hai; limit khatam ho to Groq (`gpt-oss-120b`) apne aap backup ban jaata hai. Dono ki history ek hi hai.
- **Shortcuts (bina AI):** time, date, battery, weather, volume, app kholna, PC shutdown/restart. Ye 1-2 second mein ho jaate hain.
- **Tools:** web search, weather (Open-Meteo), apps/websites kholna aur band karna, YouTube, volume/mute, screenshot, PC lock, shutdown/restart.
- **Long-term memory:** "yaad rakhna ki…", "bhool jao", "memory dikhao", "memory 2 hatao", ya type karke `remember: GitHub = xyz`.
- **Screen vision:** "screen pe kya hai", "is error ko samjhao". Screenshot sirf RAM mein rehta hai, disk pe save nahi hota.
- **WhatsApp (WhatsApp Desktop se, insaan ki tarah):** message bhejna, voice/video call lagana aur kaatna, aaye hue messages padhna. JARVIS app mein naam search karta hai, sahi chat kholta hai, confirm karta hai, tab bhejta ya call karta hai. Koi number file nahi, koi unofficial WhatsApp library nahi (ban ka risk nahi).
- **Awaaz:** ElevenLabs; wo na chale to edge-tts backup.
- **HUD UI:** `ui/index.html` frameless full-screen window: ghoomta dial aur awaaz ke saath naachti gol waveform, clock, CPU/RAM/Battery/Disk/Network, Activity (Running/Done/Failed), Weather, Conversation, aur dock buttons (Browser, YouTube, WhatsApp, Music, Files, Scan screen) + command box.
- **Background + tray:** window shuru mein chhupi rehti hai. "Jarvis wake up" pe saamne aati hai, sleep / 20s chup / Esc pe chhup jaati hai. Tray icon: **Show Jarvis** / **Quit**.

## Safety

- **Confirmation:** shutdown/restart se pehle "Sir, pakka?" poochta hai. JARVIS band karne se pehle "Sir, main band ho jaun?".
- **Safety lock:** khatarnak tools (shutdown, restart, lock, app band, volume, website kholna, screen dekhna) tabhi chalte hain jab **abhi wale message** mein wo kaam maanga gaya ho. AI purani baaton ke basis pe inhe nahi chala sakta.
- **`DRY_RUN=1`:** test mode. Shutdown, restart, lock, app band karna, WhatsApp message (Enter) aur call button sirf print hote hain, asli mein nahi chalte. WhatsApp mein chat khulti hai, par kuch bheja nahi jaata.
- **WhatsApp safety:**
  - Bhejne / call se pehle hamesha poochta hai: "PAPA ki chat khuli hai. Bhejun: '...'? Haan ya nahi".
  - Chat tabhi "khuli" maani jaati hai jab message box aur upar header, dono mein wahi naam ho. Ek naam ki kai chats milein to poochta hai "Kaunsa?".
  - Kuch bhi type/Enter karne se pehle check hota hai ki focus sahi box pe hai, WhatsApp saamne hai, aur click wali jagah pe sach mein WhatsApp hai. Galat jagah kabhi type ya click nahi.
  - PC lock ho to click nahi karta (error deta hai, atakta nahi). Chat kholne ki max 2 koshish, phir "Sir, chat nahi khul payi".
  - Privacy: WhatsApp message ka text terminal mein print nahi hota aur disk pe save nahi hota; number sirf aakhri 4 ank (`***1154`).

## Setup (Windows)

Python 3.12+ chahiye. (3.14 pe test kiya: PyAudio aur pygame ke wheels nahi the, isliye yahan `sounddevice` aur `pygame-ce` use hote hain.)

```powershell
git clone https://github.com/KRRISH972/jarvis-ai.git
cd jarvis-ai
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`Activate.ps1` pe "running scripts is disabled" aaye to pehle ye chalao:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**1. Keys:** `.env.example` ko copy karke `.env` banao aur keys bharo:

```powershell
copy .env.example .env
```

**2. WhatsApp (optional):** Microsoft Store se **WhatsApp Desktop** install karo aur login karo. Messages padhne ke liye: Windows Settings > Privacy & security > Notifications > **"Let apps access your notifications" ON**, aur Settings > System > Notifications mein **WhatsApp ON**.

**3. Vosk model (wake word ke liye, ~36 MB):** [vosk-model-small-en-in-0.4.zip](https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip) download karo aur `models\` folder mein extract karo:

```
jarvis-ai\models\vosk-model-small-en-in-0.4\
```

## Chalana

```powershell
python main.py        # Voice + HUD (window chhupi shuru hoti hai - "Jarvis wake up" ya tray > Show Jarvis)
python jarvis.py      # Sirf text chat terminal mein
```

Test mode (PC pe koi khatarnak kaam asli mein nahi hoga):

```powershell
$env:DRY_RUN = '1'; python main.py
```

**Voice commands:** "Hey Jarvis" → beep → bolo. "Jarvis sleep" / "chup raho" = sleep mode, "Jarvis shutdown" = band. 20 second chup rehne pe apne aap sleep mode.

**WhatsApp commands** (bolo ya type karo):

| Bolo | Kya hota hai |
|---|---|
| `Papa ko message bhejo ki main 7 baje aaunga` | Papa ki chat kholega, message dikha ke poochega, "haan" pe bhejega |
| `khud ko message bhejo ki test` | Apni "(You)" chat mein bhejega |
| `Papa ko call karo` / `Papa ko video call karo` | Confirm ke baad voice / video call |
| `call kaato` | Chalti WhatsApp call kaat dega |
| `messages padho` | Aaye hue WhatsApp messages (notifications se) padh ke sunayega |

Confirm pe "polite bana do" / "English mein likh do" bolo to message sudhaar ke dobara poochega.

## Files

| File | Kaam |
|---|---|
| `main.py` | Voice loop (sleep ↔ active), pywebview window (show/hide), tray icon, stats, UI chat API |
| `voice.py` | Wake word, mic, Google speech, ElevenLabs/edge-tts, beep |
| `brain.py` | Shortcut → Gemini → Groq, shared history, jawab ki safai |
| `shortcuts.py` | Bina AI wale commands (time, weather, memory…) |
| `tools.py` | Saare tools + safety lock + DRY_RUN |
| `memory.py` | `memory.json` wali long-term memory |
| `vision.py` | Screen capture + Gemini/Groq vision |
| `whatsapp.py` | WhatsApp Desktop chalana (search, chat kholna, bhejna, call, call kaatna) - pywinauto/UIA |
| `notifications.py` | Windows notifications se aaye hue WhatsApp messages (sirf RAM mein) |
| `ui.py` | Terminal + `window.jarvis` (HUD) bridge, window show/hide |
| `ui/index.html` | HUD interface (ek file: HTML + CSS + JS) |
| `jarvis.py` | Sirf text mode |

## Jo GitHub pe nahi hai (`.gitignore`)

`.env` (keys), `memory.json` (personal memory), `venv/`, `models/` (Vosk), `voice_cache/` (saved awaaz).

## Dhyan rakhna

- **Free limits:** Gemini free plan pe ~20 requests/din. Groq pe 8,000 tokens/minute, to lagatar sawaal poochne pe thoda ruk sakta hai. ElevenLabs free plan pe ~10,000 characters/mahina.
- **Internet:** HUD ka font (Chakra Petch) Google Fonts se aata hai; internet na ho to Segoe UI dikhega.
- **Band karna:** Esc = sirf window chhupao (JARVIS chalta rahe). Poora band: tray > **Quit**, Alt+F4, ya "Jarvis shutdown".
- **Design preview (bina Python):** `ui/index.html#preview` browser mein kholo - demo data ke saath HUD dikhega.
- **WhatsApp:** kaam karte waqt (2-5 second) mouse/keyboard mat chhedo. Messages sirf tab padhe jaate hain jab WhatsApp Windows notification banaye - WhatsApp saamne khula ho ya message phone pe padh liya ho to notification nahi banta.
- **Mic:** shor wale kamre mein earphone/TWS mic behtar chalta hai. Tuning `voice.py` ke upar hoti hai (`NOISE_MULTIPLIER`, `MIC_MAX_THRESHOLD`, `ECHO_GUARD_MS`).
