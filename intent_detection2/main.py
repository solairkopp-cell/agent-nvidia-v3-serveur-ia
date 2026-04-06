from intent_service import IntentService

service = IntentService()

print("=== Intent Classifier - Osias ===")
print("Tape 'quit' pour quitter\n")

while True:
    text = input("Phrase > ").strip()
    if text.lower() in ("quit", "exit", "q"):
        break
    if not text:
        continue

    intent = service.predict(text)
    proba = service.predict_proba(text)
    confidence = proba[intent] * 100

    print(f"  → Intent    : {intent}")
    print(f"  → Confiance : {confidence:.1f}%\n")