# ============================================
# phone_pair.py - Phone ko ek baar pair karo (Wireless debugging). Aap khud chalate ho: python phone_pair.py
#   Pairing code aur address screen pe print nahi hote (getpass), code kahin save nahi hota.
#   Sirf ghar ke WiFi (private IP) ka address chalta hai. Connect wala address .env PHONE_ADB_ADDRESS mein jaata hai.
# ============================================
import getpass
import os
import re
import subprocess

import phone

ENV = os.path.join(phone.BASE, ".env")


def _ask_addr(label):
    while True:
        raw = getpass.getpass(f"{label} (IP:port, screen pe nahi dikhega): ").strip()
        os.environ["PHONE_ADB_ADDRESS"] = raw
        if phone.address():
            return raw
        print("Ye ghar ke WiFi ka IP:port jaisa nahi lag raha (jaise 192.168.1.5:37000). Dobara.")


def _save_env(addr):
    lines = open(ENV, encoding="utf-8").read().splitlines() if os.path.isfile(ENV) else []
    lines = [l for l in lines if not l.startswith("PHONE_ADB_ADDRESS=")] + [f"PHONE_ADB_ADDRESS={addr}"]
    open(ENV, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main():
    print("Phone pe: Settings > Developer options > Wireless debugging > 'Pair device with pairing code'.")
    pair_addr = _ask_addr("Pairing address")
    code = getpass.getpass("6-digit pairing code: ").strip()
    if not re.fullmatch(r"\d{6}", code):
        print("Code 6 digit ka hona chahiye.")
        return
    p = subprocess.run([phone.ADB_EXE, "pair", pair_addr, code], capture_output=True, text=True, timeout=30)
    if "successfully paired" not in (p.stdout or "").lower():
        print("Pairing nahi hui. Code/address dobara dekho (code ~1 minute mein badal jaata hai).")
        return
    print("Pairing ho gayi.")
    addr = _ask_addr("Ab Wireless debugging ki MAIN screen ka 'IP address & Port'")
    _save_env(addr)
    try:
        phone.connect()
        print("Connected. Ab JARVIS se 'phone ki battery batao' bolo.")
    except phone.PhoneError as e:
        print(f"Connect nahi hua: {e}")


if __name__ == "__main__":
    main()
