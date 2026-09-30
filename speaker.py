# ============================================
# speaker.py - Sirf Krish ki awaaz (speaker verification) + shor kam (sherpa-onnx, sab offline, CPU)
#   Pipeline: recording -> VAD (sirf bolne wala hissa) -> noise suppression (gtcrn) -> speaker check -> STT
#   Match na ho to STT call hi nahi hota (voice.py chupchap ignore karta hai, sirf log mein score).
#   - voice_profile.npy = enrollment ke embeddings ka average (gitignored, kisi API ko kabhi nahi jaata).
#     Enrollment ki recordings disk pe kabhi nahi likhi jaati (sirf RAM, embedding ke baad delete).
#   - Models: models/speaker/ (gitignored), naam .env se (SPEAKER_MODEL, VAD_MODEL, DENOISE_MODEL);
#     official sherpa-onnx releases (speaker-recongition-models / speech-enhancement-models / asr-models).
#   - Profile ya model na ho to verification apne aap band (JARVIS pehle jaisa chalta hai).
#   - sherpa_onnx pehle import karo (pywebview/.NET se pehle - onnxruntime jaisa hi dhyan).
#   Terminal se: python speaker.py --score  (5 baar bolo, score dekho, kuch save nahi hota)
# ============================================
import os
import threading
import time

import numpy as np
from dotenv import load_dotenv

load_dotenv()
import sherpa_onnx  # noqa: E402  (jaldi import: .NET/pywebview load hone se pehle)

SR = 16000
BASE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE, "models", "speaker")
PROFILE_FILE = os.path.join(BASE, "voice_profile.npy")

# .env (test ke aankdon se tay hue defaults, README/CLAUDE.md mein likha hai)
VERIFY = os.getenv("SPEAKER_VERIFY", "1") == "1"
THRESHOLD = float(os.getenv("SPEAKER_THRESHOLD", "0.45"))                  # Wake ke baad pehli command + chhoti awaaz
THRESHOLD_FOLLOWUP = float(os.getenv("SPEAKER_THRESHOLD_FOLLOWUP", "0.35"))  # Baad ke 20 s ke follow-up
SPEAKER_MODEL = os.getenv("SPEAKER_MODEL", "wespeaker_en_voxceleb_CAM++_LM.onnx")
VAD_MODEL = os.getenv("VAD_MODEL", "silero_vad.onnx")
DENOISE_MODEL = os.getenv("DENOISE_MODEL", "gtcrn_simple.onnx")
DENOISE_ALWAYS = os.getenv("SPEAKER_DENOISE", "0") == "1"   # 1 = har check se pehle denoise (tez nahi: +~400 ms)
BORDERLINE = 0.15        # Threshold se itna neeche tak ka score denoise ke saath dobara check hota hai
DENOISE_STT = os.getenv("DENOISE_STT", "0") == "1"       # 1 = STT ko bhi saaf (denoised) audio do

SHORT_SECONDS = 0.6      # Isse chhoti bolne wali awaaz ka embedding unreliable: sakht (normal) threshold, follow-up wala naram nahi
MIN_ENROLL_SECONDS = 1.0

_extractor = None
_denoiser = None
_vad_config = None
_load_failed = False
_profile = None
_profile_mtime = None
enroll_requested = threading.Event()     # HUD ka "Awaaz dobara yaad karo" button (main.py loop dekhta hai)
last_seconds = 0.0       # Pichle verify + denoise mein kitna time laga ([Latency] line ke liye)
last_score = None
last_speech_seconds = 0.0


def _path(name):
    return os.path.join(MODEL_DIR, name)


def _load():
    """Models ek baar load (pehli zarurat pe). False = models nahi mile / load nahi hue."""
    global _extractor, _denoiser, _vad_config, _load_failed
    if _extractor is not None:
        return True
    if _load_failed:
        return False
    try:
        cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=_path(SPEAKER_MODEL), num_threads=1)
        _extractor = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
        vad = sherpa_onnx.VadModelConfig()
        vad.silero_vad.model = _path(VAD_MODEL)
        vad.silero_vad.threshold = 0.5
        vad.silero_vad.min_silence_duration = 0.35
        vad.silero_vad.min_speech_duration = 0.15
        vad.sample_rate = SR
        vad.num_threads = 1
        _vad_config = vad
        if os.path.exists(_path(DENOISE_MODEL)):
            dc = sherpa_onnx.OfflineSpeechDenoiserConfig()
            dc.model.gtcrn.model = _path(DENOISE_MODEL)
            dc.model.num_threads = 1
            _denoiser = sherpa_onnx.OfflineSpeechDenoiser(dc)
        return True
    except Exception as e:
        _load_failed = True
        print(f"(Speaker verification models load nahi hue: {str(e)[:100]} - verification band)")
        return False


# ---------- Profile ----------
def profile():
    """Saved voice profile (unit vector) ya None. File badle to dobara padhta hai."""
    global _profile, _profile_mtime
    try:
        m = os.path.getmtime(PROFILE_FILE)
    except OSError:
        _profile = _profile_mtime = None
        return None
    if _profile is None or m != _profile_mtime:
        try:
            v = np.load(PROFILE_FILE).astype(np.float32).ravel()
            _profile = v / (np.linalg.norm(v) + 1e-9)
            _profile_mtime = m
        except Exception:
            _profile = None
    return _profile


def enabled():
    """Verification chalu hai? (.env SPEAKER_VERIFY=1 + profile hai + models load ho gaye)"""
    return VERIFY and profile() is not None and _load()


def forget():
    """Voice profile file delete. True = thi aur hata di."""
    global _profile, _profile_mtime
    _profile = _profile_mtime = None
    try:
        os.remove(PROFILE_FILE)
        return True
    except OSError:
        return False


# ---------- Audio ----------
def to_float(audio_int16_bytes):
    return np.frombuffer(audio_int16_bytes, dtype=np.int16).astype(np.float32) / 32768.0


def speech_only(samples):
    """VAD: sirf bolne wale hisse jodkar. (audio, bolne ke seconds). VAD kuch na de to (khaali, 0)."""
    if not _load():
        return samples, len(samples) / SR
    vad = sherpa_onnx.VoiceActivityDetector(_vad_config, buffer_size_in_seconds=30)
    win = _vad_config.silero_vad.window_size
    pad = np.concatenate([samples, np.zeros(win, dtype=np.float32)])       # aakhri window poori karo
    for i in range(0, len(pad) - win + 1, win):
        vad.accept_waveform(pad[i:i + win])
    vad.flush()
    parts = []
    while not vad.empty():
        parts.append(np.array(vad.front.samples, dtype=np.float32))
        vad.pop()
    if not parts:
        return np.zeros(0, dtype=np.float32), 0.0
    out = np.concatenate(parts)
    return out, len(out) / SR


def denoise(samples):
    """gtcrn se shor kam (model na ho to jaisa hai waisa)."""
    if _denoiser is None or len(samples) == 0:
        return samples
    r = _denoiser(samples, SR)
    out = np.array(r.samples, dtype=np.float32)
    return out if r.sample_rate == SR else samples


def embed(samples):
    """Ek awaaz ka embedding (unit vector)."""
    stream = _extractor.create_stream()
    stream.accept_waveform(sample_rate=SR, waveform=samples)
    stream.input_finished()
    v = np.array(_extractor.compute(stream), dtype=np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def score_of(samples):
    """Profile se cosine score (0..1 ke aas-paas). Returns (score, bolne ke seconds, denoised audio)."""
    speech, secs = speech_only(samples)
    if secs <= 0.0:
        return 0.0, 0.0, speech
    clean = denoise(speech)
    return float(np.dot(embed(clean), profile())), secs, clean


# ---------- Commands: token se pehchano (STT ke galat roop bhi), sirf chhote command (sawaal/lambi baat nahi) ----------
import re  # noqa: E402

VOICE_TOK = {"awaaz", "awaz", "aawaz", "avaaz", "avaz", "awaj", "aavaz", "awaazein", "voice", "vois", "voise",
             "आवाज़", "आवाज", "आवाज़"}
ENROLL_TOK = {"yaad", "yad", "yaadh", "yaat", "yaadd", "record", "rekord", "enroll", "enrol", "register",
              "pehchano", "pehchan", "pahchano", "pahchan", "pehchaano", "pehchaan", "remember", "learn", "याद", "पहचानो"}
FORGET_TOK = {"bhool", "bhul", "bhoolo", "bhulo", "bhulja", "bhooljao", "hata", "hatao", "hatado", "mita", "mitao", "mitado",
              "delete", "forget", "remove", "भूल", "हटाओ", "मिटाओ"}
# Bolne ke bhare-bharaye/STT-bigde shabd (jo command ko sawaal ya lambi baat nahi banate)
FILLER_TOK = {"jarvis", "jervis", "hey", "hi", "please", "plz", "zara", "meri", "meeri", "meree", "mari", "mera", "apni", "apna",
              "my", "the", "ki", "ka", "ko", "ab", "abhi", "dobara", "phir", "fir", "se", "ek", "baar", "na", "to", "new", "again",
              "kar", "karo", "kero", "kro", "karu", "karna", "kare", "karein", "kijiye", "kijiy", "do", "de", "lo", "le", "lena",
              "dena", "rakho", "rakhna", "rakh", "jao", "ja", "jaao", "now", "and"}
_QUESTION = {"kya", "kaise", "kaisa", "kyu", "kyun", "kaun", "kab", "matlab", "meaning", "what", "how", "why", "kitna", "kitni"}


def _tokens(text):
    t = (text or "").lower()
    return [w for w in re.findall(r"[^\W_]+", t) if w]


def _voice_cmd(text, verbs):
    """Voice word + koi verb, baaki sirf filler. Sawaal ("kya", "kaise"...) ya lambi baat = False."""
    toks = _tokens(text)
    if not toks or len(toks) > 9 or set(toks) & _QUESTION:
        return False
    s = set(toks)
    if not (s & VOICE_TOK) or not (s & verbs):
        return False
    return not (s - VOICE_TOK - verbs - FILLER_TOK)


def is_forget_command(text):
    """"meri awaaz bhool jao" / "forget my voice" (STT ke galat roop bhi)."""
    return _voice_cmd(text, FORGET_TOK)


def is_enroll_command(text):
    """"meri awaaz yaad karo" / "meeri awaz yad kero" / "voice enroll" / "meri awaaz pehchano" ..."""
    return not is_forget_command(text) and _voice_cmd(text, ENROLL_TOK)


# ---------- Verify (voice.py yahin se bulata hai) ----------
def verify(samples, followup=False):
    """Return (ok, score, speech_seconds, audio_for_stt). Profile/models na ho to (True, None, ...) - chalne do.
    Chhoti awaaz (< SHORT_SECONDS) pe hamesha normal (sakht) threshold: follow-up ka naram threshold nahi.
    audio_for_stt: jaisi record hui waisi (DENOISE_STT=1 ho to VAD + denoised - abhi default nahi, WER test baaki)."""
    global last_seconds, last_score, last_speech_seconds
    if not enabled():
        last_seconds, last_score = 0.0, None
        return True, None, len(samples) / SR, samples
    t0 = time.time()
    speech, secs = speech_only(samples)
    if secs <= 0.0:
        last_seconds, last_score, last_speech_seconds = time.time() - t0, 0.0, 0.0
        return False, 0.0, 0.0, speech
    need = THRESHOLD if (not followup or secs < SHORT_SECONDS) else THRESHOLD_FOLLOWUP
    always = DENOISE_ALWAYS or DENOISE_STT
    clean = denoise(speech) if always else speech          # Denoise ~400 ms leta hai (300 ms budget se zyada)
    score = float(np.dot(embed(clean), profile()))
    if score < need and score >= need - BORDERLINE and not always:
        clean = denoise(speech)                             # Sirf borderline reject pe shor hatake ek baar aur dekho
        score = max(score, float(np.dot(embed(clean), profile())))
    last_seconds, last_score, last_speech_seconds = time.time() - t0, score, secs
    return score >= need, score, secs, (clean if DENOISE_STT else samples)


# ---------- Enrollment ----------
ENROLL_SENTENCES = [
    "Jarvis, aaj ka mausam kaisa hai?",
    "Please open Chrome and search for the latest tech news.",
    "Mera naam Krish hai aur main ye project bana raha hoon.",
    "Play some music.",
    "Kal subah saat baje mujhe yaad dilana ki gym jana hai.",
    "What is the time right now, and how much battery is left on my laptop?",
    "Volume thoda kam karo.",
    "Mere notes mein likh do ki Rahul se shaam ko chaar baje milna hai, aur uske baad film dekhne jana hai.",
    "Thank you Jarvis.",
    "Ye sab kaam ho jaye to mujhe ek chhoti si summary bata dena, phir main aage ka plan decide karunga.",
]


def build_profile(clips):
    """clips = [float32 audio, ...] -> profile save. Return (ok, message, min_similarity).
    Clips sirf RAM mein hain; yahan se koi audio disk pe nahi jaata."""
    if not _load():
        return False, "models nahi mile", 0.0
    embs = []
    for c in clips:
        speech, secs = speech_only(c)
        if secs >= MIN_ENROLL_SECONDS * 0.6:
            embs.append(embed(denoise(speech)))
    if len(embs) < 5:
        return False, f"sirf {len(embs)} vaakya theek se mile (kam se kam 5 chahiye)", 0.0
    mean = np.mean(embs, axis=0)
    mean /= (np.linalg.norm(mean) + 1e-9)
    sims = [float(np.dot(e, mean)) for e in embs]
    np.save(PROFILE_FILE, mean.astype(np.float32))
    return True, f"{len(embs)} vaakya se profile bani", min(sims)


def run_enrollment(record, prompt=None, retries=2):
    """10 vaakya: record() -> AudioData ya None (mic se ek vaakya), prompt(i, n, sentence) vaakya dikhata/bolta hai.
    Recordings sirf RAM mein; profile tabhi badalti hai jab nayi ban jaaye. Return (ok, message, sabse alag vaakya ki samanta)."""
    if not _load():
        return False, "models nahi mile", 0.0
    clips, misses = [], 0
    n = len(ENROLL_SENTENCES)
    for i, sentence in enumerate(ENROLL_SENTENCES, 1):
        for _ in range(retries):
            if prompt:
                prompt(i, n, sentence)
            audio = record()
            if audio is not None:
                samples = to_float(audio.frame_data)
                if speech_only(samples)[1] >= 0.8:
                    clips.append(samples)
                    misses = 0
                    break
            misses += 1
            if misses >= 3:
                break
        if misses >= 3:
            break
    if misses >= 3:
        return False, "awaaz nahi suni", 0.0
    result = build_profile(clips)
    del clips                                   # Recordings ka koi nishaan nahi
    return result


if __name__ == "__main__":
    # python speaker.py --score      : 5 baar bolo, har baar ka score (koi audio save nahi, koi STT nahi)
    # python speaker.py --calibrate  : 5 baar aap + 5 baar koi aur / TV -> threshold ka sujhav
    import sys
    import sounddevice as sd

    def _record(prompt):
        input(prompt)
        rec = sd.rec(int(3.5 * SR), samplerate=SR, channels=1, dtype="float32")
        sd.wait()
        return rec[:, 0]

    if not ("--score" in sys.argv or "--calibrate" in sys.argv):
        sys.exit("python speaker.py --score  ya  --calibrate")
    if not enabled():
        sys.exit("Profile nahi hai (pehle 'Jarvis meri awaaz yaad karo') ya models nahi mile.")
    print(f"Threshold: normal {THRESHOLD}, follow-up {THRESHOLD_FOLLOWUP}.")
    mine = []
    for i in range(5):
        _, score, secs, _a = verify(_record(f"[aap {i + 1}/5] Enter dabake ek chhota vaakya bolo (~3 second)... "))
        mine.append(score)
        print(f"   score {score:.2f}, bola {secs:.1f}s, verify {last_seconds * 1000:.0f} ms")
    if "--calibrate" in sys.argv:
        others = []
        for i in range(5):
            _, score, secs, _a = verify(_record(f"[dusra/TV {i + 1}/5] Ab koi DUSRA insaan bole ya TV/YouTube chalao, phir Enter... "))
            others.append(score)
            print(f"   score {score:.2f}")
        lo, hi = min(mine), max(others)
        print(f"\nAap: min {lo:.2f}, average {np.mean(mine):.2f} | Dusre: max {hi:.2f}")
        if lo > hi:
            print(f"Sujhav: SPEAKER_THRESHOLD={(lo + hi) / 2:.2f}, SPEAKER_THRESHOLD_FOLLOWUP={max(hi + 0.02, (lo + hi) / 2 - 0.08):.2f}")
        else:
            print(f"Awaazein overlap kar rahi hain (aap ka min {lo:.2f} <= dusre ka max {hi:.2f}). Threshold {lo - 0.03:.2f} tak "
                  "rakhoge to aap kabhi nahi kategen par dusre bhi nikal sakte hain; dobara enrollment (shant jagah, 10 vaakya) try karo.")
