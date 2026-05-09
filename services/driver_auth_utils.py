"""
Utilitaires d'identification vocale driver.
"""
from __future__ import annotations

import re
import unicodedata


_DIGIT_WORDS = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "zéro": "0",
    "zero": "0",
    "un": "1",
    "une": "1",
    "deux": "2",
    "trois": "3",
    "quatre": "4",
    "cinq": "5",
    "six": "6",
    "sept": "7",
    "huit": "8",
    "neuf": "9",
}


def extract_driver_serial_from_transcript(transcript: str) -> str | None:
    """
    Extraire une suite de chiffres depuis une transcription Whisper.

    Exemples:
      - "driver number 00123" -> "00123"
      - "zero zero one two three" -> "00123"
      - "zéro zéro un deux trois" -> "00123"
    """
    text = _normalize(transcript)
    if not text:
        return None

    digits: list[str] = []
    for token in re.findall(r"\d+|[a-zA-ZÀ-ÿ]+", text):
        if token.isdigit():
            digits.append(token)
            continue
        digit = _DIGIT_WORDS.get(token)
        if digit is not None:
            digits.append(digit)

    serial = "".join(digits)
    return serial or None


def _normalize(text: str) -> str:
    lowered = (text or "").strip().lower()
    if not lowered:
        return ""
    # Garder aussi les accents originaux dans le mapping, mais supprimer les
    # diacritiques pour les transcriptions qui varient selon Whisper.
    normalized = unicodedata.normalize("NFKD", lowered)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))
