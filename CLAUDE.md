# CLAUDE.md - JARVIS project guide

JARVIS is Krish's personal Windows voice assistant, written in Python. Krish speaks (or types) in Hinglish, and JARVIS listens, thinks, controls the PC and replies in a British voice. It has a full-screen sci-fi HUD (pywebview) and runs in the background with a system tray icon.

- Repo: https://github.com/KRRISH972/jarvis-ai (private, branch `main`)
- Path: `D:\JARVIS`, Windows 11, **Python 3.14** in `venv\`
- The user writes in Hinglish (Roman script). Reply to the user in Roman Hinglish.

## Rules (always follow)

1. **Tests always run with `DRY_RUN=1`.** Set it on the test process (`DRY_RUN=1 ./venv/Scripts/python.exe ...` in Bash, `$env:DRY_RUN='1'` in PowerShell). Never change `DRY_RUN` in `.env` for tests; `.env` stays `DRY_RUN=0` for normal use. In DRY_RUN, shutdown/restart/lock/close_app/WhatsApp send/call only print what they would do.
2. **Side-effect tools must be faked in tests.** Opening apps, websites, YouTube, volume, mute and WhatsApp actions must be faked in BOTH places: `tools.<name>` and `brain.TOOLS_BY_NAME[<name>]` (brain keeps its own copy of the tool list). Missing the second one once opened YouTube for real during a test.
3. **Commit and push finished work** to `origin main` (use `C:\Program Files\GitHub CLI\gh.exe` if `gh` is needed; plain `git push` works). Never commit `.env`, `memory.json`, `venv/`, `models/`, `voice_cache/`. Do not push half-finished or failing work; commit locally and say so.
4. **Safety lock:** dangerous/visible tools only run when the user's CURRENT message contains a matching word (`tools._asked_for`, `needs=` on `@tool`). AI must never act on old history. Keep this for every new tool.
5. **Confirm before risky actions:** shutdown/restart, closing JARVIS, sending WhatsApp, WhatsApp calls, "forget all memory".
6. **Privacy:** phone numbers only as last 4 digits (`whatsapp.mask`). WhatsApp message text (incoming and outgoing) is never printed to the terminal (`voice.speak(..., private=True)`, `tools.private_reply`), never saved to disk. When probing the user's apps (WhatsApp UI etc.), print only control types / UI labels / counts, never chat names, previews or numbers.
7. **Language:** replies in the user's language and script. Roman Hinglish input gets Roman Hinglish output, never Devanagari (see `brain.SYSTEM_PROMPT`, `brain._tidy`).
8. **Don't invent data:** no made-up phone numbers, and never claim an action happened unless a tool returned success in this turn.
9. Code comments are in Hinglish, docstrings that the AI reads (tool docstrings) are in English.

## How to run

```powershell
cd D:\JARVIS
.\venv\Scripts\Activate.ps1
$env:DRY_RUN = '1'; python main.py   # voice + HUD (window starts hidden; "Jarvis wake up" or tray > Show Jarvis)
python jarvis.py                     # text-only chat in terminal
```

`.env` keys: `GEMINI_API_KEY`, `GROQ_API_KEY`, `GROQ_MODEL` (openai/gpt-oss-120b), `GROQ_VISION_MODEL` (qwen/qwen3.8-27b), `GROQ_REASONING_EFFORT` (low), `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `DRY_RUN`. Template: `.env.example`.

## Files

| File | Job |
|---|---|
| `main.py` | Voice loop (sleep mode ↔ active mode), control commands ("Jarvis sleep/shutdown", "chup raho"), latency line, confirmation by voice (`voice_confirm`, `voice_ask`), WhatsApp announcements, pywebview window (frameless, fullscreen, starts hidden, show on wake / hide on sleep & Esc), tray icon (pystray), stats thread, `Api.ask` for typed chat |
| `voice.py` | Vosk offline wake word (noise measured in sleep mode), mic recording with sounddevice (threshold cap, echo guard, pre-roll), Google speech (en-IN then hi-IN), beep, `speak()` with ElevenLabs → edge-tts fallback, cache for fixed lines, loudness envelope for the HUD |
| `brain.py` | `ask()`: shortcut → Gemini → Groq fallback, shared history, dynamic system prompt (memories + last WhatsApp sender), tool schemas for Groq, `DirectReply` handling, memory read-back, reply cleanup (`_tidy`), spelled-letter joining (`join_spelled`), `rewrite_message` |
| `shortcuts.py` | No-AI commands: time/date/battery (keyword + filler words), weather, volume/mute, open apps/sites, PC shutdown/restart, memory commands (typed `remember:`, list, delete by number, corrections/undo), WhatsApp commands (send, call, end call, read, reply) |
| `tools.py` | All tools with `@tool` decorator (UI log + action card + safety lock + try/except), `DRY_RUN`, `DirectReply(ok=...)`, `confirm` / `ask_user` hooks, weather (Open-Meteo), vision, memory, WhatsApp tools |
| `memory.py` | Long-term memory in `memory.json` (gitignored): add/update/undo/remove, numbered list, spelled read-back |
| `vision.py` | Screenshot in RAM (mss, max 1280px) → Gemini, fallback Groq vision (qwen) |
| `whatsapp.py` | WhatsApp Desktop UI automation with pywinauto (search, open chat, send, call, end call) |
| `notifications.py` | Reads WhatsApp notifications from Windows (pywinrt `UserNotificationListener`), kept only in RAM |
| `ui.py` | Terminal print + `window.jarvis` bridge (`setState`, `log`, `wake`, `sleep`, `addMessage`, `setStats`, `setWeather`, `action`, `setLevel`), window show/hide |
| `ui/index.html` | Single-file HUD (HTML+CSS+JS). `#preview` hash shows demo data in a browser (used for Edge headless screenshots) |
| `jarvis.py` | Text mode; sets typed `confirm` / `ask_user` |
| `README.md` | User-facing setup guide (includes WhatsApp setup, commands, safety) |

Python 3.14 notes: PyAudio and pygame have no wheels, so the project uses `sounddevice` and `pygame-ce`; `winsdk` does not install, so notifications use `winrt-*` (pywinrt) packages.

## Features (working)

- Wake word "Hey Jarvis" / "Jarvis wake up" (Vosk, offline); sleep via "Jarvis sleep", "sleep mode on", "chup raho", or 20 s of silence; exit via "Jarvis shutdown" with confirmation.
- Brain: Gemini main (free tier ~20 requests/day, often exhausted), Groq backup (8,000 tokens/min limit, each call ~1.4k tokens).
- Shortcuts without AI for time, date, battery, weather, volume, apps, PC shutdown/restart, memory.
- Tools: web search (ddgs), weather (Open-Meteo), open/close apps and sites, YouTube, volume/mute, screenshot, lock, shutdown/restart, memory, screen vision.
- Memory: save with exact read-back and spelling ("K-R-R-I-S-H-9-7-2. Sahi hai?"), "galat hai" = undo, "memory dikhao", "memory 2 hatao", typed `remember: X = Y`.
- HUD: states, waveform with real voice level, stats (CPU/RAM/battery/disk/net), weather panel, activity cards, conversation, dock buttons, typed commands.

## WhatsApp feature - current status (WORK IN PROGRESS)

Design (user's request): no number files and no unofficial WhatsApp libraries. JARVIS drives WhatsApp Desktop like a person: search the name, pick the chat (ask if several), read the chat header, confirm, then paste + Enter (or press the call button). `contacts.json`, `contacts.example.json` and Phone Link calls were removed on purpose.

WhatsApp Desktop (package `5319275A.WhatsAppDesktop`, v2.2637) is WhatsApp Web inside WebView2. Known UI facts:
- Main window class `WinUIDesktopWin32WindowClass`; title can be `(10) WhatsApp` (unread count prefix), so match `\bwhatsapp$`. When closed it hides in the tray: always `os.startfile(APP_ID)` first.
- Search box placeholder name is `Search or start a new chat`, but **its name becomes empty when it has text**, so it is found by position (topmost Edit that is not the message box).
- Results: `DataGrid` named `Search results.` with `DataItem` rows; section header rows `Chats` / `Contacts` / `Messages`. Rows after `Messages` are matches inside message text and must be skipped. Inside a row, the shortest-named `DataItem` is "name + date"; the long ones contain previews or the disappearing-timer text ("Change timer") and must never be clicked.
- Open chat is identified by the message box name `Type a message to <chat name>` AND the chat header (wide Button at the top of the right column whose name contains the chat name). The user's own chat is `+91 … (You)`; it is NOT pinned, so it is found in the `Chat list` DataGrid (never by searching `You`, which also matches names like Yash).
- Speed/focus facts: find the page (`RootWebArea`) with native UIA `FindFirst` (~0.05s; pywinauto `descendants()`/`child_window()` took ~6s each). The global focused element is only the WebView `Pane`, so focus is checked with the element's own `HasKeyboardFocus`. Clicking on the lock screen hangs `SetCursorPos` forever, so `_click` checks `desktop_ready()` first.
- Empty message box value is a single `\n`.

What works (DRY_RUN tests on the real app):
- Opening the user's own "(You)" chat and reading its name; confirm question; no Enter or call button pressed in DRY_RUN; "not found" for an unknown name; UI action cards per step; fake "several results → Kaunsa?" picking by name or ordinal.
- Incoming notifications: permission is already Allowed on this PC; announcements, "messages padho", reply flow and privacy were tested with fake notifications only.

What is NOT done / not verified:
- Opening chats is fixed and verified (DRY_RUN, real app): own "(You)" chat 3/3 (~0.7s, click), a real contact 5/5 (~2.9s, keyboard Down+Enter and click both work), unknown name -> "naam nahi mila" with nothing typed anywhere else. Max 2 open tries, no re-search; paste/Enter only after a focus check.
- Real send verified once (2026-09-27, to a real contact: paste + Enter + "message appeared" check OK). Real voice call + end call verified once: header buttons are `Video call` / `Voice call` (own chat has none); the call opens a separate WhatsApp window with `End call`, found by process id. `_click` refuses to click unless WhatsApp (or the given owner window) is in front and under the click point. Real video call + end verified once too. Reading real messages NOT done yet: listener works (permission Allowed, other apps' toasts are read), but a real incoming WhatsApp message (unread in the chat list) created no Windows toast, so "messages padho" found nothing. Next time: check WhatsApp notifications are ON (Windows Settings > System > Notifications, and inside WhatsApp), keep WhatsApp minimized, do not open the message on the phone, then re-check counts only.
