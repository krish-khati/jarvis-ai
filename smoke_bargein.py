# Chhota smoke test: barge-in "stop" pe trigger, JARVIS ki line pe nahi. DRY_RUN=1 ke saath chalao.
import asyncio, io, os, subprocess, sys, tempfile
os.environ["DRY_RUN"] = "1"
import numpy as np, edge_tts, voice, brain
import main  # noqa: F401  (import check)

def pcm(text, voice_name, amp=1.0):
    mp3 = os.path.join(tempfile.gettempdir(), "smk.mp3")
    asyncio.run(edge_tts.Communicate(text, voice_name).save(mp3))
    import pygame
    pygame.mixer.quit(); pygame.mixer.init(frequency=16000, size=-16, channels=1)
    raw = pygame.mixer.Sound(mp3).get_raw()
    a = (np.frombuffer(raw, np.int16) * amp).astype(np.int16)
    return np.concatenate([np.zeros(16000, np.int16), a, np.zeros(16000, np.int16)]).tobytes()

def run(audio):
    b = voice.BargeIn(warmup_ms=0)
    b.reset()
    for i in range(0, len(audio) - 1279 * 2, 2560):
        if b.feed(audio[i:i + 2560]): return True
    return False

# JARVIS ki goonj = uski apni line dheemi (mic pe echo); goonj se gate banta hai, phir user "stop" bolta hai
echo = pcm("Sir, aaj ka mausam kaisa hai? Bahut garmi hai aur dhoop tez hai.", "en-GB-RyanNeural", amp=0.15)
assert not run(echo), "JARVIS ki line pe trigger ho gaya"
assert run(echo + pcm("Stop stop stop!", "en-US-GuyNeural")), "stop pe trigger nahi hua"
print("SMOKE OK")
