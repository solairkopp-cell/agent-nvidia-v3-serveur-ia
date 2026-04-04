"""
tests/test_vad_service.py
Tests unitaires du VADService.
Le modèle ONNX est mocké — pas de dépendance externe.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from models.session import Session
from services.vad_service import VADResult, VADService


@pytest.fixture
def session(tmp_path):
    ws_mock = MagicMock()
    return Session(client_id="test-client", websocket=ws_mock)


@pytest.fixture
def vad():
    service = VADService()
    # Simuler le modèle chargé (évite de charger le vrai ONNX)
    service._model = MagicMock(return_value=0.0)
    service._chunk_samples = 512
    service._silence_threshold = 15   # 480ms / 32ms
    service._min_speech_chunks = 10   # 300ms / 32ms
    service._start_trigger_chunks = 2
    service._pre_roll_chunks = 2
    service._post_roll_chunks = 2
    return service


def make_chunk(n=512) -> np.ndarray:
    return np.zeros(n, dtype=np.float32)


class TestVADProcessChunk:

    def test_silence_when_no_speech(self, vad, session):
        """Score bas → silence."""
        vad._model.return_value = 0.1
        result = vad.process_chunk(session, make_chunk())
        assert result.type == "silence"
        assert not session.is_speaking

    def test_isolated_speech_chunk_does_not_trigger_start(self, vad, session):
        """Un seul chunk > seuil ne suffit plus à déclencher speech_start."""
        vad._model.return_value = 0.9
        result = vad.process_chunk(session, make_chunk())
        assert result.type == "silence"
        assert not session.is_speaking

    def test_speech_start_after_consecutive_speech_chunks(self, vad, session):
        """Deux chunks de parole consécutifs → speech_start."""
        vad._model.return_value = 0.9
        first = vad.process_chunk(session, make_chunk())
        second = vad.process_chunk(session, make_chunk())
        assert first.type == "silence"
        assert second.type == "speech_start"
        assert session.is_speaking

    def test_speech_start_includes_pre_roll(self, vad, session):
        """Le speech_start récupère aussi le pré-roll et les chunks de confirmation."""
        vad._model.return_value = 0.1
        pre_a = np.ones(512, dtype=np.float32)
        pre_b = np.ones(512, dtype=np.float32) * 2
        vad.process_chunk(session, pre_a)
        vad.process_chunk(session, pre_b)

        speech_a = np.ones(512, dtype=np.float32) * 3
        speech_b = np.ones(512, dtype=np.float32) * 4
        vad._model.return_value = 0.9
        first = vad.process_chunk(session, speech_a)
        result = vad.process_chunk(session, speech_b)

        assert first.type == "silence"
        assert result.type == "speech_start"
        assert len(session.audio_buffer) == 4
        np.testing.assert_array_equal(session.audio_buffer[0], pre_a)
        np.testing.assert_array_equal(session.audio_buffer[1], pre_b)
        np.testing.assert_array_equal(session.audio_buffer[2], speech_a)
        np.testing.assert_array_equal(session.audio_buffer[3], speech_b)

    def test_speech_continues_after_start(self, vad, session):
        """Chunks de parole suivants → speech."""
        vad._model.return_value = 0.9
        vad.process_chunk(session, make_chunk())
        vad.process_chunk(session, make_chunk())  # speech_start
        result = vad.process_chunk(session, make_chunk())
        assert result.type == "speech"

    def test_continue_threshold_is_more_permissive_than_start(self, vad, session, monkeypatch):
        """Après speech_start, un score plus bas peut rester en parole grâce à l'hysteresis."""
        monkeypatch.setattr("config.VAD_SILENCE_THRESHOLD", 0.6)
        monkeypatch.setattr("config.VAD_CONTINUE_THRESHOLD", 0.45)
        vad._model.side_effect = [0.7, 0.7, 0.5]

        first = vad.process_chunk(session, make_chunk())
        second = vad.process_chunk(session, make_chunk())
        third = vad.process_chunk(session, make_chunk())

        assert first.type == "silence"
        assert second.type == "speech_start"
        assert third.type == "speech"

    def test_utterance_end_after_silence(self, vad, session):
        """
        Assez de parole puis assez de silence → utterance_end avec audio.
        """
        # Générer suffisamment de chunks de parole
        vad._model.return_value = 0.9
        for _ in range(vad._min_speech_chunks + 1):
            vad.process_chunk(session, make_chunk())

        # Puis assez de silence
        vad._model.return_value = 0.1
        result = None
        for _ in range(vad._silence_threshold + vad._post_roll_chunks):
            result = vad.process_chunk(session, make_chunk())

        assert result is not None
        assert result.type == "utterance_end"
        assert result.audio is not None
        assert isinstance(result.audio, np.ndarray)

    def test_utterance_end_includes_post_roll(self, vad, session):
        """L'audio final inclut les chunks de silence de post-roll."""
        vad._model.return_value = 0.9
        for _ in range(vad._min_speech_chunks):
            vad.process_chunk(session, make_chunk())

        vad._model.return_value = 0.1
        result = None
        for _ in range(vad._silence_threshold + vad._post_roll_chunks):
            result = vad.process_chunk(session, make_chunk())

        assert result is not None
        assert result.type == "utterance_end"
        assert result.audio is not None
        expected_chunks = vad._min_speech_chunks + vad._silence_threshold + vad._post_roll_chunks
        assert result.audio.shape[0] == expected_chunks * vad._chunk_samples

    def test_short_utterance_ignored(self, vad, session):
        """Utterance trop courte → ignorée (pas d'utterance_end)."""
        vad._model.return_value = 0.9
        # Moins de min_speech_chunks
        for _ in range(3):
            vad.process_chunk(session, make_chunk())

        vad._model.return_value = 0.1
        results = []
        for _ in range(vad._silence_threshold + vad._post_roll_chunks):
            results.append(vad.process_chunk(session, make_chunk()))

        types = [r.type for r in results]
        assert "utterance_end" not in types
        assert not session.is_speaking

    def test_buffer_reset_after_utterance_end(self, vad, session):
        """Après utterance_end, le buffer est réinitialisé."""
        session.pre_speech_buffer.append(make_chunk())

        vad._model.return_value = 0.9
        for _ in range(vad._min_speech_chunks + 1):
            vad.process_chunk(session, make_chunk())

        vad._model.return_value = 0.1
        for _ in range(vad._silence_threshold + vad._post_roll_chunks):
            vad.process_chunk(session, make_chunk())

        assert not session.is_speaking
        assert session.silence_chunks == 0
        assert session.speech_chunks == 0
        assert len(session.audio_buffer) == 0
        assert len(session.pre_speech_buffer) == 0
        assert session.post_roll_chunks == 0
