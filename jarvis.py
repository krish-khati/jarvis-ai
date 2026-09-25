# ============================================
# JARVIS - Text mode (terminal mein type karke chat)
# Voice mode ke liye main.py chalao
# ============================================

import sys

# Terminal mein Hindi/emoji jaise characters print karte waqt crash na ho
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import brain   # AI wala saara kaam (Gemini + Groq backup, history) brain.py mein hai
import tools   # Tools - text mode mein confirmation type karke lenge


def text_confirm(question):
    """Khatarnak kaam (shutdown/restart) se pehle type karke poochho."""
    answer = input(f"JARVIS: {question} (haan/nahi): ").strip().lower()
    return answer in ("haan", "han", "ha", "yes", "y", "pakka")


tools.confirm = text_confirm


# --- Chat loop ---
print("JARVIS online hai. Band karne ke liye 'exit' ya 'bye' likho.\n")

while True:
    # User se input lo (.strip() aage-peeche ke extra spaces hata deta hai)
    user_input = input("Krish: ").strip()

    # Khaali input ho to dobara poochho
    if not user_input:
        continue

    # 'exit' ya 'bye' likhne pe loop band karo
    if user_input.lower() in ("exit", "bye"):
        print("JARVIS: Bye Krish! Phir milte hain.")
        break

    # Message Gemini ko bhejo aur jawab print karo
    try:
        reply = brain.ask(user_input)
        print(f"JARVIS: {reply}\n")
    except Exception as e:
        # Internet ya API mein problem ho to program crash nahi hoga
        print(f"JARVIS: Kuch gadbad ho gayi - {e}\n")
