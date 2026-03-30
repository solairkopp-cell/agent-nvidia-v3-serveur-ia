"""
services/tts_utils.py
Common text segmentation utilities for TTS services (Piper, etc.).
"""
import re
import config

STRONG_PUNCTUATION = set(".!?")
SOFT_PUNCTUATION = set(",:;—")
ALL_PUNCTUATION = STRONG_PUNCTUATION | SOFT_PUNCTUATION

COORDINATION_CONJUNCTIONS = {"and", "but", "or", "nor", "so", "yet", "for"}
SUBORDINATION_CONJUNCTIONS = {
    "when", "where", "while", "because", "although", "though", "if",
    "unless", "until", "since", "after", "before", "as",
}
RELATIVE_PRONOUNS = {"which", "that", "who", "whom", "whose"}
TRANSITION_ADVERBS = {"however", "therefore", " meanwhile", "instead", "otherwise", "finally", "then"}
TRANSITION_ADVERBS = {word.strip() for word in TRANSITION_ADVERBS}
MODAL_VERBS = {"can", "will", "should", "must", "would", "could", "may", "might", "shall"}


def extract_tts_ready_segments(text: str, final: bool = False) -> tuple[list[str], str]:
    """
    Extraire les segments prêts pour la synthèse TTS.
    Segmentation sur frontières naturelles, avec fallback à `TTS_STREAM_WORD_CHUNK_SIZE`.
    """
    buffer = text or ""
    word_chunk_size = max(1, int(getattr(config, "TTS_STREAM_WORD_CHUNK_SIZE", 7)))
    return _extract_dynamic_word_chunks(buffer, chunk_size=word_chunk_size, final=final)


def _extract_dynamic_word_chunks(text: str, chunk_size: int, final: bool) -> tuple[list[str], str]:
    if chunk_size <= 0:
        return [], text or ""

    raw = text or ""
    processable, trailing_fragment = _split_processable_text(raw, final=final)
    if not processable and not trailing_fragment:
        return [], ""

    completed_clauses, open_clause = _split_completed_clauses(processable)
    segments: list[str] = []
    for clause in completed_clauses:
        segments.extend(_split_clause_naturally(clause, chunk_size))

    open_clause = _join_text_parts(open_clause, trailing_fragment)
    if final:
        if open_clause:
            segments.extend(_split_clause_naturally(open_clause, chunk_size))
        return segments, ""

    open_segments, rest = _emit_open_clause_naturally(open_clause, chunk_size)
    segments.extend(open_segments)
    return segments, rest


def _split_processable_text(text: str, final: bool) -> tuple[str, str]:
    raw = text or ""
    if not raw:
        return "", ""
    if final or _ends_with_complete_token(raw):
        return raw.strip(), ""

    last_space = raw.rfind(" ")
    if last_space == -1:
        return "", raw.strip()
    return raw[:last_space].strip(), raw[last_space + 1 :].strip()


def _split_completed_clauses(text: str) -> tuple[list[str], str]:
    clauses: list[str] = []
    if not text:
        return clauses, ""

    current: list[str] = []
    for index, ch in enumerate(text):
        current.append(ch)
        if ch in ALL_PUNCTUATION and not _is_decimal_punctuation(text, index):
            clause = "".join(current).strip()
            if clause:
                clauses.append(clause)
            current = []

    rest = "".join(current).strip()
    return clauses, rest


def _split_clause_naturally(text: str, chunk_size: int) -> list[str]:
    clause = _normalize_text(text)
    if not clause:
        return []

    terminal_punctuation = _extract_terminal_punctuation(clause)
    core = clause[:-1].strip() if terminal_punctuation else clause
    words = core.split()
    if not words:
        return []

    segments: list[str] = []
    while len(words) > chunk_size:
        split_index = _find_natural_split_index(words, chunk_size)
        left_words = words[:split_index]
        segments.append(_join_words(left_words))
        words = words[split_index:]

    tail = _join_words(words)
    if tail:
        if terminal_punctuation:
            tail = f"{tail}{terminal_punctuation}"
        segments.append(tail)
    return segments


def _emit_open_clause_naturally(text: str, chunk_size: int) -> tuple[list[str], str]:
    clause = _normalize_text(text)
    if not clause:
        return [], ""

    words = clause.split()
    if len(words) < chunk_size:
        return [], clause

    emitted: list[str] = []
    while len(words) >= chunk_size:
        split_index = _find_natural_split_index(words, chunk_size)
        emitted.append(_join_words(words[:split_index]))
        words = words[split_index:]

    rest = " ".join(words).strip()
    return emitted, rest


def _normalize_text(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _extract_terminal_punctuation(text: str) -> str:
    if not text:
        return ""
    last = text[-1]
    if last in ALL_PUNCTUATION and not _is_decimal_punctuation(text, len(text) - 1):
        return last
    return ""


def _find_natural_split_index(words: list[str], chunk_size: int) -> int:
    if len(words) <= chunk_size:
        return len(words)

    max_index = min(len(words) - 1, chunk_size)
    min_index = 3 if max_index >= 3 else 1

    for lexicon in (
        SUBORDINATION_CONJUNCTIONS,
        COORDINATION_CONJUNCTIONS,
        RELATIVE_PRONOUNS,
        TRANSITION_ADVERBS,
    ):
        index = _find_boundary_before_word(words, lexicon, min_index, max_index)
        if index is not None:
            return index

    index = _find_modal_boundary(words, min_index, max_index)
    if index is not None:
        return index

    index = _find_infinitive_boundary(words, min_index, max_index)
    if index is not None:
        return index

    return max_index


def _find_boundary_before_word(words: list[str], lexicon: set[str], min_index: int, max_index: int) -> int | None:
    for index in range(max_index, min_index - 1, -1):
        if _normalized_word(words[index]) in lexicon:
            return index
    return None


def _find_modal_boundary(words: list[str], min_index: int, max_index: int) -> int | None:
    upper = min(max_index - 1, len(words) - 2)
    for index in range(upper, min_index - 1, -1):
        if _normalized_word(words[index]) in MODAL_VERBS:
            return index + 1
    return None


def _find_infinitive_boundary(words: list[str], min_index: int, max_index: int) -> int | None:
    for index in range(max_index, min_index - 1, -1):
        if _normalized_word(words[index]) == "to":
            return index
    return None


def _join_words(words: list[str]) -> str:
    return " ".join(words).strip()


def _join_text_parts(left: str, right: str) -> str:
    parts = [part.strip() for part in (left, right) if part and part.strip()]
    return " ".join(parts).strip()


def _normalized_word(word: str) -> str:
    return re.sub(r"^[^\w]+|[^\w]+$", "", word or "").strip().lower()


def _ends_with_complete_token(text: str) -> bool:
    if not text:
        return False
    last = text[-1]
    return last.isspace() or last in ALL_PUNCTUATION


def _is_decimal_punctuation(text: str, index: int) -> bool:
    if index <= 0 or index >= len(text) - 1:
        return False
    return text[index] == "." and text[index - 1].isdigit() and text[index + 1].isdigit()
