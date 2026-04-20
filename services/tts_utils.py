"""
services/tts_utils.py
Simple text segmentation for TTS services (Piper, etc.).
Split on sentence boundaries: . : ; ! ? and ...
"""
import re


_SENTENCE_PATTERN = re.compile(r".+?(?:\.\.\.(?!\.)|[.:;!?](?!\.))")


def extract_tts_ready_segments(text: str, final: bool = False) -> tuple[list[str], str]:
    """
    Extraire les segments prêts pour la synthèse TTS.
    Segmentation simple sur : . : ; ! ? et ...
    
    En mode streaming (final=False) : garde le dernier segment incomplet dans le buffer.
    En mode final (final=True) : retourne tout le texte restant.
    """
    buffer = text or ""
    
    if not buffer.strip():
        return [], ""
    
    if final:
        # En mode final, on retourne tout le buffer restant
        return [buffer.strip()], ""

    matches = list(_SENTENCE_PATTERN.finditer(buffer))
    if matches:
        segments = [match.group(0).strip() for match in matches if match.group(0).strip()]
        last_end = matches[-1].end()
        remaining = buffer[last_end:].strip() if last_end < len(buffer) else ""
        return segments, remaining

    return [], buffer.strip()
