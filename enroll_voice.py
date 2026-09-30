# ============================================
# enroll_voice.py - Awaaz yaad karwao, bina STT / bina JARVIS ke (seedha mic se 10 vaakya)
#   python enroll_voice.py
#   Har vaakya screen pe aata hai: beep ke baad use apni normal awaaz mein bolo.
#   Recordings sirf RAM mein, disk pe kabhi nahi; sirf voice_profile.npy banta hai (gitignored, kisi API ko nahi jaati).
#   (JARVIS chal raha ho to pehle use band karo: dono ek saath mic nahi le sakte.)
# ============================================
import speaker
import voice          # mic recording (_record_until_silence) + beep


def main():
    if not speaker._load():
        print("Speaker models nahi mile (models/speaker/). CLAUDE.md dekho.")
        return 1

    def prompt(i, n, sentence):
        print(f"\n[{i}/{n}]  {sentence}")
        voice.beep()

    print("10 vaakya bolne hain. Shant jagah pe, apni normal awaaz mein. Har vaakya ke beep ke baad bolo.")
    ok, msg, worst = speaker.run_enrollment(lambda: voice._record_until_silence(wait_seconds=10), prompt)
    print(("\nProfile ban gayi: " if ok else "\nNahi bani: ") + msg)
    if ok:
        print(f"Sabse alag vaakya ki samanta {worst:.2f}" + ("  (kam hai - shant jagah pe dobara karo)" if worst < 0.35 else ""))
        print("Ab JARVIS chalao. Threshold set karne ke liye: python speaker.py --calibrate")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
