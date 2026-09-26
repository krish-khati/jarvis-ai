# J.A.R.V.I.S

Krish ka personal AI assistant: Hinglish mein bolo ya type karo, JARVIS sunta hai, sochta hai, PC chalata hai aur British awaaz mein jawab deta hai. 3D HUD window ke saath.

## Kya-kya karta hai

- **Wake word (offline):** "Hey Jarvis" / "Jarvis wake up" pe jaagta hai. Vosk se chalta hai, internet nahi chahiye, CPU kam lagta hai.
- **Sunna:** Google speech (en-IN, na samjhe to hi-IN), aur spell kiye naam jodta hai ("k r r i s h 9 7 2" → `krrish972`).
- **Dimaag:** Gemini main brain hai; limit khatam ho to Groq (`gpt-oss-120b`) apne aap backup ban jaata hai. Dono ki history ek hi hai.
- **Shortcuts (bina AI):** time, date, battery, weather, volume, app kholna, PC shutdown/restart. Ye 1-2 second mein ho jaate hain.
- **Tools:** web search, weather (Open-Meteo), apps/websites kholna aur band karna, YouTube, volume/mute, screenshot, PC lock, shutdown/restart.
- **Long-term memory:** "yaad rakhna ki…", "bhool jao", "memory dikhao", "memory 2 hatao", ya type karke `remember: GitHub = xyz`.
- **Screen vision:** "screen pe kya hai", "is error ko samjhao". Screenshot sirf RAM mein rehta hai, disk pe save nahi hota.
- **Awaaz:** ElevenLabs; wo na chale to edge-tts backup.
- **3D UI:** `ui/index.html` pywebview window mein khulta hai (orb, chat, stats, activity log).

## Safety

- **Confirmation:** shutdown/restart se pehle "Sir, pakka?" poochta hai. JARVIS band karne se pehle "Sir, main band ho jaun?".
- **Safety lock:** khatarnak tools (shutdown, restart, lock, app band, volume, website kholna, screen dekhna) tabhi chalte hain jab **abhi wale message** mein wo kaam maanga gaya ho. AI purani baaton ke basis pe inhe nahi chala sakta.
- **`DRY_RUN=1`:** test mode. Shutdown, restart, lock aur app band karna sirf print hote hain, asli mein nahi chalte.

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

**2. Vosk model (wake word ke liye, ~36 MB):** [vosk-model-small-en-in-0.4.zip](https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip) download karo aur `models\` folder mein extract karo:

```
jarvis-ai\models\vosk-model-small-en-in-0.4\
```

## Chalana

```powershell
python main.py        # Voice + 3D UI window (Alt+F4 = band)
python jarvis.py      # Sirf text chat terminal mein
```

Test mode (PC pe koi khatarnak kaam asli mein nahi hoga):

```powershell
$env:DRY_RUN = '1'; python main.py
```

**Voice commands:** "Hey Jarvis" → beep → bolo. "Jarvis sleep" / "chup raho" = sleep mode, "Jarvis shutdown" = band. 20 second chup rehne pe apne aap sleep mode.

## Files

| File | Kaam |
|---|---|
| `main.py` | Voice loop (sleep ↔ active), pywebview window, UI chat API |
| `voice.py` | Wake word, mic, Google speech, ElevenLabs/edge-tts, beep |
| `brain.py` | Shortcut → Gemini → Groq, shared history, jawab ki safai |
| `shortcuts.py` | Bina AI wale commands (time, weather, memory…) |
| `tools.py` | Saare tools + safety lock + DRY_RUN |
| `memory.py` | `memory.json` wali long-term memory |
| `vision.py` | Screen capture + Gemini/Groq vision |
| `ui.py` | Terminal + `window.jarvis` (3D UI) bridge |
| `ui/index.html` | 3D HUD interface |
| `jarvis.py` | Sirf text mode |

## Jo GitHub pe nahi hai (`.gitignore`)

`.env` (keys), `memory.json` (personal memory), `venv/`, `models/` (Vosk), `voice_cache/` (saved awaaz).

## Dhyan rakhna

- **Free limits:** Gemini free plan pe ~20 requests/din. Groq pe 8,000 tokens/minute, to lagatar sawaal poochne pe thoda ruk sakta hai. ElevenLabs free plan pe ~10,000 characters/mahina.
- **Internet:** 3D UI ka orb (three.js) aur fonts internet se aate hain.
- **Mic:** shor wale kamre mein earphone/TWS mic behtar chalta hai. Tuning `voice.py` ke upar hoti hai (`NOISE_MULTIPLIER`, `MIC_MAX_THRESHOLD`, `ECHO_GUARD_MS`).
