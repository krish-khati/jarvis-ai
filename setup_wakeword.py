# Ek baar chalao: openWakeWord ke "hey_jarvis" + feature models models\openwakeword\ mein download karta hai (~9 MB)
#   pip install --no-deps openwakeword      (pehle, agar nahi kiya)
#   python setup_wakeword.py

import os

import wakeword

wakeword._import_model_class()        # openwakeword package import (scipy/sklearn stub ke saath)
import openwakeword.utils as utils    # noqa: E402

os.makedirs(wakeword.MODEL_DIR, exist_ok=True)
utils.download_models(model_names=["hey_jarvis"], target_directory=wakeword.MODEL_DIR)
print("Models:", ", ".join(sorted(os.listdir(wakeword.MODEL_DIR))))
