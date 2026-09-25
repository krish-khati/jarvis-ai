# ============================================
# voice.py - JARVIS ke kaan aur muh
#   - wait_for_wake_word() : Vosk se offline "Hey Jarvis" sunna
#   - listen_command()     : Google se command sunna (English/Hindi/Hinglish)
#   - speak()              : ElevenLabs se bolna (backup: edge-tts), pygame se play
#
# Note: Mic ke liye PyAudio ki jagah "sounddevice" use kiya hai, kyunki
# PyAudio Windows (Python 3.14) pe install nahi hota. Kaam same hai.
# ============================================

import asyncio             # edge-tts async hai, use chalane ke liye
import hashlib             # Saved awaaz files ke naam banane ke liye
import json                # Vosk ka result JSON mein aata hai
import os                  # File paths ke liye
import queue               # Mic se aaye audio ke tukde store karne ke liye
import re                  # Text mein Hindi letters dhoondhne ke liye
import tempfile            # Awaaz ki mp3 file temporary folder mein rakhne ke liye
import time                # Latency (kitne second lage) naapne ke liye

import numpy as np                 # Awaaz kitni tez hai (volume) naapne ke liye
import sounddevice as sd           # Mic se audio record karne ke liye
import speech_recognition as sr    # Google speech-to-text ke liye
import vosk                        # Offline wake word detection ke liye
import edge_tts                    # Microsoft ki free text-to-speech awaaz (backup)
from dotenv import load_dotenv     # .env se ElevenLabs key padhne ke liye
from elevenlabs.client import ElevenLabs   # ElevenLabs ki awaaz (main)
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"   # pygame ka welcome message chhupao
import pygame                      # mp3 file play karne ke liye

import ui                          # Screen pe status (kya suna, kisne bola)


# --- Settings ---
SAMPLE_RATE = 16000        # 16kHz - speech recognition ke liye standard
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "vosk-model-small-en-in-0.4")

# ElevenLabs (main awaaz) - key aur voice ID .env file se aati hai
load_dotenv()
ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVEN_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")  # default: George
# Flash model: tez hai, Hindi/English/Hinglish teeno bolta hai, aur credits kam khata hai.
# Aur achhi (par mehngi) awaaz chahiye to "eleven_multilingual_v2" try karo.
ELEVEN_MODEL = "eleven_flash_v2_5"

# edge-tts (backup awaaz) - jab ElevenLabs kaam na kare
ENGLISH_VOICE = "en-GB-RyanNeural"     # British awaaz (JARVIS jaisi)
HINDI_VOICE = "hi-IN-MadhurNeural"     # Hindi awaaz

# Wake word phrases (Vosk sirf inhi words ko pehchanne ki koshish karega)
WAKE_PHRASES = ["hey jarvis", "jarvis wake up"]
SHUTDOWN_PHRASES = ["jarvis shutdown", "jarvis shut down"]


# --- Setup (program shuru hote hi ek baar chalta hai) ---
vosk.SetLogLevel(-1)       # Vosk ke faltu log messages band karo

if not os.path.isdir(MODEL_PATH):
    print(f"Error: Vosk model nahi mila: {MODEL_PATH}")
    print("Download: https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip")
    print("Zip ko D:\\JARVIS\\models\\ folder mein extract karo.")
    raise SystemExit(1)

vosk_model = vosk.Model(MODEL_PATH)    # Offline model memory mein load karo
recognizer = sr.Recognizer()           # Google speech recognizer
pygame.mixer.init()                    # pygame ka audio player chalu karo

# --- Beep: listening shuru hone ka ishaara ("ab bolo") ---
BEEP_ENABLED = True          # Beep nahi chahiye to False karo
_need_beep = False           # JARVIS abhi bola hai -> agli listening pe beep bajao


def _make_beep(freq=880, ms=120, volume=0.25):
    """Chhoti "ting" awaaz memory mein banao (koi file nahi). pygame ke format
    (sample rate, channels) ke hisaab se."""
    rate, _, channels = pygame.mixer.get_init()
    t = np.arange(int(rate * ms / 1000)) / rate
    wave = np.sin(2 * np.pi * freq * t) * volume
    wave *= np.minimum(1, np.minimum(t, t[::-1]) * 200)      # Shuru/end mein "click" na ho
    samples = (wave * 32767).astype(np.int16)
    if channels == 2:
        samples = np.column_stack([samples, samples])
    return pygame.sndarray.make_sound(samples)


_beep_sound = None


def beep():
    """Beep bajao aur khatam hone tak ruko (taaki mic beep ko na sune)."""
    global _beep_sound
    if not BEEP_ENABLED:
        return
    if _beep_sound is None:
        _beep_sound = _make_beep()
    ch = _beep_sound.play()
    while ch is not None and ch.get_busy():
        pygame.time.wait(10)
    ui.log("Beep (listening started - ab boliye)")

# Bolne wali awaaz yahan save hogi
SPEECH_FILE = os.path.join(tempfile.gettempdir(), "jarvis_speech.mp3")

# Latency ke liye: aakhri baar Google ko sunne mein aur awaaz banane mein kitne second lage
last_stt_seconds = 0.0
last_tts_seconds = 0.0

# --- Mic settings (background noise pe galti se na chale) ---
# Bolna = room ke shor se kitne guna tez awaaz. Shor pe bhi chal jaaye to badhao (jaise 4.0)
NOISE_MULTIPLIER = 3.0
# Kam se kam itni tez awaaz ho tabhi "bolna" maano. Aapki awaaz na pakde to ghatao (jaise 350)
MIC_MIN_THRESHOLD = 500
# Zyada se zyada itna - warna shor wale kamre mein threshold itna upar chala jaata hai
# (7000-12000) ki aapki awaaz pakdi hi nahi jaati aur JARVIS "behra" ho jaata hai
MIC_MAX_THRESHOLD = 3000
# JARVIS ki awaaz khatam hone ke baad itne milliseconds ruko, phir mic kholo
# (laptop speaker ki goonj mic mein na aaye). Goonj phir bhi aaye to badhao (jaise 700)
POST_SPEECH_GAP_MS = 150
# Mic khulne ke baad pehle itne ms tak koi awaaz recording SHURU nahi kar sakti (speaker ki
# goonj pe trigger na ho) - lekin wo audio pre-roll mein rakha jaata hai, taaki agar aap
# turant bolna shuru karo to pehla word na kate. Gap + guard = 0.55s goonj se bachav.
ECHO_GUARD_MS = 400

# Background noise SLEEP MODE mein naapte hain (jab JARVIS chup hai aur speaker band hai)
# aur wahi yaad rakhte hain. Listening mein dobara nahi naapte - kyunki tab JARVIS abhi
# bola hota hai aur mic uski goonj ko "shor" samajh leta hai.
noise_level = None           # Sleep mode mein naapa hua shor (None = abhi naapa nahi)
_noise_samples = []          # Sleep mode ke aakhri kuch tukdon ki awaaz
START_BLOCKS = 3             # 3 x 0.1s = 0.3 second lagatar awaaz ho tab recording shuru
PRE_ROLL_BLOCKS = 8          # 8 x 0.1s = bolna pakadne se 0.8 second PEHLE ka audio bhi rakho
                             # (taaki pehla word na kate - jaise "joke sunao" ka "joke",
                             # ya echo guard ke beech shuru hua bolna)
MIN_SPEECH_SECONDS = 0.4     # Isse chhoti awaaz = shor, Google ko nahi bhejte
_last_threshold = 0.0        # Pichla threshold (sirf badalne pe dikhane ke liye)
_said_not_understood = False # "samajh nahi aaya" pehle hi dikha chuke? (baar-baar na dikhe)
_warned_noisy = False        # "bahut shor hai" warning pehle hi dikha chuke?

# Fixed lines ki saved awaaz yahan rahegi (ElevenLabs characters bachane ke liye)
CACHE_DIR = os.path.join(os.path.dirname(__file__), "voice_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# ElevenLabs client - key nahi hai to seedha edge-tts use hoga
use_elevenlabs = bool(ELEVEN_API_KEY)
eleven_client = ElevenLabs(api_key=ELEVEN_API_KEY) if use_elevenlabs else None


# ============================================
# 1. WAKE WORD - Vosk (offline, kam CPU)
# ============================================
def wait_for_wake_word():
    """Chupchap sunta rehta hai jab tak "Hey Jarvis" / "Jarvis wake up"
    (return "wake") ya "Jarvis shutdown" (return "shutdown") na sune."""

    # Grammar = Vosk ko bata do ki sirf ye words sunne hain.
    # Isse CPU kam lagta hai aur galat detection bhi kam hoti hai.
    # "[unk]" = baaki koi bhi awaaz ("unknown")
    grammar = json.dumps(WAKE_PHRASES + SHUTDOWN_PHRASES + ["jarvis", "[unk]"])
    rec = vosk.KaldiRecognizer(vosk_model, SAMPLE_RATE, grammar)

    # Mic se aane wala audio is queue mein aata rahega
    audio_queue = queue.Queue()

    def on_audio(indata, frames, time, status):
        # Ye function sounddevice khud har audio tukde ke liye call karta hai
        audio_queue.put(bytes(indata))

    # Mic stream kholo (0.5 second ke tukde, 16-bit mono)
    with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000,
                           dtype="int16", channels=1, callback=on_audio):
        while True:
            data = audio_queue.get()
            _update_noise(data)      # Chupchap room ka shor naapte raho

            # AcceptWaveform True deta hai jab ek poora sentence khatam ho
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result())["text"]
                # Test ke liye: wake word ne kya suna (akele "jarvis"/"down" jaise
                # tukde shor hote hain - sirf 2+ words wale dikhao)
                if len(text.replace("[unk]", "").split()) >= 2:
                    ui.log(f"Vosk heard: {text}")

                if any(p in text for p in WAKE_PHRASES):
                    return "wake"
                if any(p in text for p in SHUTDOWN_PHRASES):
                    return "shutdown"


def _update_noise(data):
    """Sleep mode ke har 0.5s tukde se room ka shor naapo.
    Aakhri 20 tukdon (10 second) ka neeche wala hissa (30th percentile) lete hain -
    taaki beech mein aapka "Hey Jarvis" bolna shor na gina jaaye."""
    global noise_level
    level = np.abs(np.frombuffer(data, dtype=np.int16)).mean()
    _noise_samples.append(level)
    del _noise_samples[:-20]
    noise_level = float(np.percentile(_noise_samples, 30))


# ============================================
# 2. COMMAND SUNNA - SpeechRecognition (Google)
# ============================================
def _record_until_silence(wait_seconds=8, silence_seconds=1.2, max_seconds=15):
    """Mic se tab tak record karta hai jab tak user bolna band na kare.
    Agar wait_seconds tak koi kuch na bole (ya sirf shor ho) to None return karta hai."""
    global _last_threshold

    block = int(SAMPLE_RATE * 0.1)     # 0.1 second ke tukdon mein padho

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        # Room ka shor: sleep mode mein naapa hua use karo (JARVIS ki goonj se bacha hua).
        # Sirf tab yahan naapo jab abhi tak kabhi naapa hi nahi (bahut rare)
        if noise_level is not None:
            noise, source = noise_level, "sleep mode mein naapa"
        else:
            noise = np.mean([np.abs(stream.read(block)[0]).mean() for _ in range(5)])
            source = "abhi naapa"
        threshold = min(max(noise * NOISE_MULTIPLIER, MIC_MIN_THRESHOLD), MIC_MAX_THRESHOLD)

        # Bahut shor hai -> ek baar batao (limit ki wajah se ab shor pe bhi recording
        # shuru ho sakti hai, par Google shor ko samjhega nahi - earphone mic behtar hai)
        global _warned_noisy
        if noise * NOISE_MULTIPLIER > MIC_MAX_THRESHOLD and not _warned_noisy:
            ui.log(f"Mic: bahut shor hai (noise {noise:.0f}) - earphone/TWS mic behtar rahega")
            _warned_noisy = True

        # Threshold kaafi badla ho tabhi dikhao (har baar same line na aaye)
        if abs(threshold - _last_threshold) > 0.3 * max(_last_threshold, 1):
            ui.log(f"Mic: background noise {noise:.0f} ({source}), bolne ka threshold {threshold:.0f}")
            _last_threshold = threshold

        chunks = []          # Recorded audio yahan jama hoga
        loud_run = []        # Lagatar tez tukde (bolna shuru hua ya sirf "tak" jaisi awaaz?)
        recent = []          # Bolna shuru hone se pehle ke aakhri tukde (pre-roll ke liye)
        started = False      # User ne bolna shuru kiya ya nahi
        speech_time = 0.0    # Kitni der tak sach mein awaaz tez thi
        silent_time = 0.0    # Kitni der se chup hai
        total_time = 0.0     # Kul kitna time hua

        while total_time < max_seconds:
            data, _ = stream.read(block)
            total_time += 0.1
            loud = np.abs(data).mean() > threshold

            if not started:
                # Bolna tabhi maano jab 0.3 second LAGATAR tez awaaz ho -
                # darwaza, click, pankha jaisi chhoti awaazein ignore
                # Echo guard: shuru ke 0.4s mein tez awaaz (goonj ho sakti hai) recording
                # shuru nahi karti - par neeche "recent" mein audio rakha jaata hai
                can_start = total_time * 1000 > ECHO_GUARD_MS
                loud_run = loud_run + [data] if (loud and can_start) else []
                # Pichle kuch tukde yaad rakho - pehle word ki dheemi shuruaat
                # ("joke" ka "j") threshold se neeche hoti hai, wo katni nahi chahiye
                recent = (recent + [data])[-(PRE_ROLL_BLOCKS + START_BLOCKS):]
                if len(loud_run) >= START_BLOCKS:
                    started = True          # Bolna shuru!
                    # Recording = pre-roll (0.5s pehle ka) + tez awaaz wale tukde
                    chunks.extend(recent)
                    speech_time = 0.1 * len(loud_run)
                elif total_time > wait_seconds:
                    return None             # Koi kuch nahi bola
                continue

            chunks.append(data)
            if loud:
                speech_time += 0.1
                silent_time = 0.0
            else:
                silent_time += 0.1
            if silent_time >= silence_seconds:
                break                       # User chup ho gaya, recording khatam

    # Bahut chhoti awaaz = shor hai, Google ko mat bhejo (time + "samajh nahi aaya" bachta hai)
    if speech_time < MIN_SPEECH_SECONDS:
        return None

    # Numpy audio ko SpeechRecognition wale format mein badlo
    raw = np.concatenate(chunks).tobytes()
    return sr.AudioData(raw, SAMPLE_RATE, 2)   # 2 = 16-bit (2 bytes)


def listen_command(wait_seconds=8):
    """User ka command sunta hai aur text return karta hai.
    Kuch samajh na aaye ya koi na bole to None return karta hai."""

    global last_stt_seconds, _said_not_understood, _need_beep
    # JARVIS abhi bola tha -> beep bajao taaki pata chale ab bolna hai
    # (khaali intezaar ke baad dobara sunte waqt beep nahi - warna har 8s beep)
    if _need_beep:
        _need_beep = False
        beep()
    audio = _record_until_silence(wait_seconds=wait_seconds)
    if audio is None:
        return None
    started = time.time()     # Latency: Google ko text banane mein kitna laga

    # Pehle English (India) mein try karo - ye English + Hinglish dono
    # (Roman letters mein) samajh leta hai. Na samjhe to Hindi mein try karo.
    for language in ("en-IN", "hi-IN"):
        try:
            text = recognizer.recognize_google(audio, language=language)
            last_stt_seconds = time.time() - started
            ui.log(f"Heard ({language}, {last_stt_seconds:.1f}s): {text}")
            _said_not_understood = False
            return text
        except sr.UnknownValueError:
            continue                        # Samajh nahi aaya, agli language
        except sr.RequestError as e:
            print(f"Google speech service error (internet check karo): {e}")
            return None

    # Dono language mein samajh nahi aaya - lagatar kai baar ho to bhi sirf ek line dikhao
    if not _said_not_understood:
        ui.log("Heard: (samajh nahi aaya)")
        _said_not_understood = True
    return None


# ============================================
# 3. BOLNA - edge-tts + pygame
# ============================================

# Common Hinglish words - agar reply mein ye kaafi hain to Hindi awaaz use karo,
# warna British awaaz Hinglish ko ajeeb tarah se bolegi
HINGLISH_WORDS = {"hai", "hain", "hoon", "hu", "main", "mein", "kya", "aap", "aapka",
                  "nahi", "raha", "rahi", "karo", "kar", "ka", "ki", "ke", "ko",
                  "theek", "acha", "accha", "haan", "bhi", "tum", "mera", "tera"}


def _pick_voice(text):
    """Text dekh ke decide karta hai ki Hindi awaaz chahiye ya English."""
    # Devanagari (हिंदी) letters hain to seedha Hindi awaaz
    if re.search(r"[ऀ-ॿ]", text):
        return HINDI_VOICE
    # Roman Hinglish: 2 ya zyada Hinglish words mile to Hindi awaaz
    words = re.findall(r"[a-z]+", text.lower())
    if sum(w in HINGLISH_WORDS for w in words) >= 2:
        return HINDI_VOICE
    return ENGLISH_VOICE


def _elevenlabs_mp3(text, path):
    """ElevenLabs se awaaz banake mp3 file save karta hai.
    Kaam na kare to False return karta hai (tab edge-tts backup chalega)."""
    global use_elevenlabs

    if not use_elevenlabs:
        return False

    try:
        # Awaaz tukdon (chunks) mein aati hai - sabko jod ke ek file banao
        audio = eleven_client.text_to_speech.convert(
            voice_id=ELEVEN_VOICE_ID,
            model_id=ELEVEN_MODEL,
            text=text,
            output_format="mp3_44100_128",
        )
        with open(path, "wb") as f:
            f.write(b"".join(audio))
        return True
    except Exception as e:
        status = getattr(e, "status_code", None)
        print(f"(ElevenLabs error {status or ''}, edge-tts se bol raha hoon)")
        # 401/402/403 = limit khatam ya key ki problem -> is session mein
        # dobara try mat karo. Internet ki chhoti problem pe agli baar phir try hoga.
        if status in (401, 402, 403):
            use_elevenlabs = False
        return False


ENVELOPE_MS = 50     # Orb ke liye awaaz har 50ms pe naapte hain


def _loudness_envelope(path):
    """mp3 ko samples mein kholo aur har 50ms ki loudness (0..1) ki list do.
    UI window na ho to kuch nahi karte (time bachao). Error pe khaali list."""
    if ui.window is None:
        return []
    try:
        rate, _, channels = pygame.mixer.get_init()
        samples = pygame.sndarray.array(pygame.mixer.Sound(path)).astype(np.float32)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)                    # Stereo -> mono
        step = int(rate * ENVELOPE_MS / 1000)
        chunks = [np.sqrt(np.mean(samples[i:i + step] ** 2)) for i in range(0, len(samples), step)]
        peak = max(max(chunks), 1.0)
        return [min(1.0, (c / peak) ** 0.7) for c in chunks]  # 0.7 = dheemi awaaz bhi dikhe
    except Exception:
        return []


def speak(text, cache=False, show=True):
    """Text ko awaaz mein bolta hai (bolna khatam hone tak rukta hai).
    cache=True: fixed lines (jaise "Yes sir...") ek baar banake save ho jaati
    hain, agli baar se wahi file chalti hai - ElevenLabs ke characters bachte hain.
    show=False: UI chat mein mat daalo (jaise wake line - wo jarvis.wake() khud dikhata hai)."""
    global last_tts_seconds
    print(f"JARVIS: {text}")
    if show:
        ui.add_message("ai", text)     # UI chat mein JARVIS ki line
    started = time.time()     # Latency: awaaz banane mein kitna laga

    # Gemini kabhi-kabhi *bold* ya # heading bhejta hai - bolne se pehle hatao
    # ("_" nahi hatate - "krrish_972" jaise username ka hissa ho sakta hai)
    clean = re.sub(r"[*#`]", "", text).strip()
    if not clean:
        return

    path = SPEECH_FILE
    if cache:
        # Har line (+ voice) ki apni file - naam text ke hash se banta hai
        name = hashlib.md5(f"{ELEVEN_VOICE_ID}|{clean}".encode()).hexdigest()
        path = os.path.join(CACHE_DIR, name + ".mp3")

    # Cache mein file pehle se hai to seedha play karo, warna nayi banao
    if cache and os.path.exists(path):
        ui.log("Voice: saved file (cache, no ElevenLabs characters used)")
    else:
        # 1st choice: ElevenLabs. Fail ho to backup: edge-tts
        if _elevenlabs_mp3(clean, path):
            ui.log(f"Voice: ElevenLabs ({ELEVEN_MODEL})")
        else:
            if cache:
                path = SPEECH_FILE    # edge-tts wali awaaz cache mat karo
            edge_voice = _pick_voice(clean)
            try:
                asyncio.run(edge_tts.Communicate(clean, edge_voice).save(path))
                ui.log(f"Voice: edge-tts ({edge_voice})")
            except Exception as e:
                print(f"(Awaaz nahi ban payi: {e})")
                return

    last_tts_seconds = time.time() - started

    # Awaaz ka "envelope" pehle se nikaal lo - har 50ms kitni tez hai (0..1),
    # taaki bolte waqt UI ka orb awaaz ke saath naache
    envelope = _loudness_envelope(path)

    # pygame se mp3 play karo aur khatam hone tak ruko
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        if envelope:
            pos = pygame.mixer.music.get_pos() // ENVELOPE_MS      # Abhi kaunsa 50ms ka tukda
            ui.set_level(envelope[min(max(pos, 0), len(envelope) - 1)])
        pygame.time.wait(40)
    ui.set_level(0)                 # Bolna khatam - orb shaant
    pygame.mixer.music.unload()     # File chhodo taaki agli baar overwrite ho sake
    # Thoda ruko taaki speaker ki goonj khatam ho jaaye - warna mic JARVIS ki
    # apni awaaz ko aapka bolna samajh ke record karna shuru kar deta hai
    pygame.time.wait(POST_SPEECH_GAP_MS)
    global _need_beep
    _need_beep = True        # Agli listening shuru hone pe beep
