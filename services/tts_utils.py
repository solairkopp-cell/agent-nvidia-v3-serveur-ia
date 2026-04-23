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
    Segmentation sur : . : ; ! ? et ...
    Une phrase doit avoir au minimum 4 mots pour être envoyée, 
    sinon on attend la ponctuation suivante.
    """
    buffer = text or ""
    
    if not buffer.strip():
        return [], ""
    
    if final:
        # En mode final, on retourne tout le buffer restant
        return [buffer.strip()], ""

    matches = list(_SENTENCE_PATTERN.finditer(buffer))
    if not matches:
        return [], buffer.strip()

    segments = []
    current_segment = ""
    last_end = 0

    for match in matches:
        part = match.group(0).strip()
        if not part:
            continue
            
        current_segment = (current_segment + " " + part).strip()
        
        # Vérifie si le segment accumulé a au moins 4 mots
        if len(current_segment.split()) >= 4:
            segments.append(current_segment)
            current_segment = ""
            last_end = match.end()

    # Le texte non validé (par ex < 4 mots) reste dans 'remaining'
    remaining = buffer[last_end:].strip() if last_end < len(buffer) else ""
    return segments, remaining
