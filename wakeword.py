# ============================================
# wakeword.py - openWakeWord ka pretrained "hey_jarvis" model (ONNX, CPU pe halka)
#   Sleep mode mein voice.wait_for_wake_word() isse "Hey Jarvis" pehchanta hai.
#   Vosk backup hai ("Jarvis wake up" / "Jarvis shutdown" phrases ke liye).
#   Threshold .env ke WAKE_THRESHOLD se (zyada = kam galat jaagna, par kabhi kabhi miss).
# ============================================

import os
import sys
import types

import numpy as np
import onnxruntime  # noqa: F401  - webview/.NET se PEHLE load hona zaroori (baad mein import karne pe crash)
from dotenv import load_dotenv

load_dotenv()

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "openwakeword")
MODEL_FILE = os.path.join(MODEL_DIR, "hey_jarvis_v0.1.onnx")
FRAME = 1280                    # 80 ms @ 16 kHz - openWakeWord ka frame size

# .env se: score is se upar (lagatar PATIENCE frames) to jaago
THRESHOLD = float(os.getenv("WAKE_THRESHOLD", "0.5"))
PATIENCE = int(os.getenv("WAKE_PATIENCE", "2"))       # Lagatar itne 80ms-frames threshold ke upar hone chahiye
ENABLED = os.getenv("WAKE_OPENWAKEWORD", "1") != "0"


def _import_model_class():
    """openwakeword ka __init__ training wale module (scipy/sklearn) bhi import karta hai, jinki
    inference mein zarurat nahi (aur wo bhaari hain). Import ke waqt chhote stub laga ke bachate hain."""
    stubs = {"scipy": {}, "sklearn": {}, "sklearn.linear_model": {"LogisticRegression": object},
             "sklearn.pipeline": {"make_pipeline": object},
             "sklearn.preprocessing": {"FunctionTransformer": object, "StandardScaler": object}}
    added = []
    for name, attrs in stubs.items():
        if name not in sys.modules:
            m = types.ModuleType(name)
            m.__dict__.update(attrs)
            sys.modules[name] = m
            added.append(name)
    try:
        from openwakeword.model import Model
    finally:
        for name in added:            # Stub hata do (kuch aur scipy chahe to asli import ho)
            sys.modules.pop(name, None)
    return Model


class WakeDetector:
    """80 ms ke int16 tukde do (feed), "Hey Jarvis" pe True milta hai."""

    def __init__(self, threshold=THRESHOLD, patience=PATIENCE):
        Model = _import_model_class()
        self.model = Model(
            wakeword_models=[MODEL_FILE], inference_framework="onnx",
            melspec_model_path=os.path.join(MODEL_DIR, "melspectrogram.onnx"),
            embedding_model_path=os.path.join(MODEL_DIR, "embedding_model.onnx"))
        self.name = next(iter(self.model.models))
        self.threshold, self.patience = threshold, patience
        self.run = 0            # Lagatar kitne frames threshold ke upar
        self.last_score = 0.0
        self.peak = 0.0         # Is baar ka sabse bada score (log ke liye)
        self.buf = np.zeros(0, dtype=np.int16)

    def score(self, pcm):
        """int16 audio (koi bhi length) -> is chunk ka sabse bada score (0..1)."""
        self.buf = np.concatenate([self.buf, pcm])
        best = 0.0
        while len(self.buf) >= FRAME:
            frame, self.buf = self.buf[:FRAME], self.buf[FRAME:]
            s = float(self.model.predict(frame)[self.name])
            self.last_score = s
            best = max(best, s)
            self.peak = max(self.peak, s)
            self.run = self.run + 1 if s >= self.threshold else 0
        return best

    def detected(self, pcm):
        """Audio do; True agar wake word (patience frames tak) threshold ke upar raha."""
        self.score(pcm)
        if self.run >= self.patience:
            self.model.reset()          # peak log ke liye bacha rehta hai; agli reset() zero karegi
            self.run = 0
            return True
        return False

    def reset(self):
        self.run = 0
        self.model.reset()
        self.peak = 0.0


def available():
    return ENABLED and os.path.isfile(MODEL_FILE)
