"""
services/tts_utils.py
Simple text segmentation for TTS services (Piper, etc.).
Split on sentence boundaries: . : ! ? and ...
"""
import re
import config


def extract_tts_ready_segments(text: str, final: bool = False) -> tuple[list[str], str]:
    """
    Extraire les segments prêts pour la synthèse TTS.
    Segmentation simple sur : . : ! ? et ...
    
    En mode streaming (final=False) : garde le dernier segment incomplet dans le buffer.
    En mode final (final=True) : retourne tout le texte restant.
    """
    buffer = text or ""
    
    if not buffer.strip():
        return [], ""
    
    if final:
        # En mode final, on retourne tout le buffer restant
        return [buffer.strip()], ""
    
    # Mode streaming : on découpe sur les délimiteurs
    # Pattern pour capturer les segments terminés par : ... (prioritaire) ou . : ! ?
    # On utilise un lookahead pour s'assurer que ... n'est pas suivi d'un autre .
    pattern = r'(.+?(?:\.\.\.(?!\.)|[.:!?](?!\.)))'
    
    parts = re.findall(pattern, buffer)
    
    if not parts:
        # Aucun délimiteur trouvé → tout reste dans le buffer
        return [], buffer.strip()
    
    # Tous les segments complets sauf le dernier → prêts à être synthétisés
    segments = [p.strip() for p in parts[:-1] if p.strip()]
    
    # Le dernier segment trouvé + le reste non-matché → reste dans le buffer
    last_complete = parts[-1].strip() if parts else ""
    
    # Trouver où se termine le dernier segment matché
    last_match_end = 0
    for match in re.finditer(pattern, buffer):
        last_match_end = match.end()
    
    remaining = buffer[last_match_end:].strip() if last_match_end < len(buffer) else ""
    
    # Le dernier segment complet reste dans le buffer en mode streaming
    if last_complete:
        remaining = f"{last_complete} {remaining}".strip() if remaining else last_complete
    
    return segments, remaining
