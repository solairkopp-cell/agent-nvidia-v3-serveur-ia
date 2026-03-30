"""
tests/test_kokoro_tts_service.py
Tests ciblés sur le découpage TTS actuel.
"""
from __future__ import annotations

from services.kokoro_tts_service import extract_tts_ready_segments


def test_extract_tts_ready_segments_splits_on_subordination_frontier(monkeypatch):
    monkeypatch.setattr("config.TTS_STREAM_WORD_CHUNK_SIZE", 7)

    text = "We keep the audio stable when the next phrase arrives."
    segments, rest = extract_tts_ready_segments(text, final=False)

    assert segments == [
        "We keep the audio stable",
        "when the next phrase arrives.",
    ]
    assert rest == ""


def test_extract_tts_ready_segments_splits_on_coordination_frontier(monkeypatch):
    monkeypatch.setattr("config.TTS_STREAM_WORD_CHUNK_SIZE", 7)

    text = "The buffer stays warm and the playback remains smooth."
    segments, rest = extract_tts_ready_segments(text, final=False)

    assert segments == [
        "The buffer stays warm",
        "and the playback remains smooth.",
    ]
    assert rest == ""


def test_extract_tts_ready_segments_preserves_punctuation_delimited_parts(monkeypatch):
    monkeypatch.setattr("config.TTS_STREAM_WORD_CHUNK_SIZE", 7)

    text = "Bonjour a tous, nous arrivons maintenant pour la demo finale."
    segments, rest = extract_tts_ready_segments(text, final=False)

    assert segments == [
        "Bonjour a tous,",
        "nous arrivons maintenant pour la demo finale.",
    ]
    assert rest == ""


def test_extract_tts_ready_segments_falls_back_to_seven_words(monkeypatch):
    monkeypatch.setattr("config.TTS_STREAM_WORD_CHUNK_SIZE", 7)

    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    segments, rest = extract_tts_ready_segments(text, final=False)

    assert segments == ["alpha beta gamma delta epsilon zeta eta"]
    assert rest == "theta iota kappa lambda"
