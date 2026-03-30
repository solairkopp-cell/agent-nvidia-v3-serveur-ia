"""
tests/test_tts_utils.py
Tests pour la segmentation de texte TTS.
"""
import pytest

from services.tts_utils import extract_tts_ready_segments


class TestExtractTtsReadySegments:

    def test_split_on_period(self):
        """Découpe sur le point."""
        segments, remaining = extract_tts_ready_segments("Bonjour. Comment ça va?")
        assert segments == ["Bonjour."]
        assert remaining == "Comment ça va?"

    def test_split_on_exclamation(self):
        """Découpe sur le point d'exclamation."""
        segments, remaining = extract_tts_ready_segments("Hello! How are you?")
        assert segments == ["Hello!"]
        assert remaining == "How are you?"

    def test_split_on_question(self):
        """Découpe sur le point d'interrogation."""
        segments, remaining = extract_tts_ready_segments("Qui êtes-vous? Je suis là.")
        assert segments == ["Qui êtes-vous?"]
        assert remaining == "Je suis là."

    def test_split_on_colon(self):
        """Découpe sur les deux-points."""
        segments, remaining = extract_tts_ready_segments("Voici la liste: premier élément. Deuxième élément.")
        # Le premier segment s'arrête au ':', le suivant au '.'
        assert segments == ["Voici la liste:", "premier élément."]
        assert remaining == "Deuxième élément."

    def test_split_on_ellipsis(self):
        """Découpe sur les points de suspension."""
        segments, remaining = extract_tts_ready_segments("Attendez... Je réfléchis. Oui.")
        assert segments == ["Attendez...", "Je réfléchis."]
        assert remaining == "Oui."

    def test_multiple_delimiters(self):
        """Multiple délimiteurs dans le même texte."""
        segments, remaining = extract_tts_ready_segments("Bonjour! Comment allez-vous? Très bien, merci. Et vous?")
        assert segments == ["Bonjour!", "Comment allez-vous?", "Très bien, merci."]
        assert remaining == "Et vous?"

    def test_final_mode_returns_all(self):
        """En mode final, retourne tout le texte restant."""
        segments, remaining = extract_tts_ready_segments("Texte incomplet", final=True)
        assert segments == ["Texte incomplet"]
        assert remaining == ""

    def test_final_mode_with_punctuation(self):
        """En mode final avec ponctuation."""
        segments, remaining = extract_tts_ready_segments("Texte complet.", final=True)
        assert segments == ["Texte complet."]
        assert remaining == ""

    def test_empty_input(self):
        """Texte vide."""
        segments, remaining = extract_tts_ready_segments("")
        assert segments == []
        assert remaining == ""

    def test_no_delimiter_yet(self):
        """Pas encore de délimiteur → reste dans le buffer."""
        segments, remaining = extract_tts_ready_segments("Bonjour le monde")
        assert segments == []
        assert remaining == "Bonjour le monde"

    def test_whitespace_handling(self):
        """Gestion des espaces."""
        segments, remaining = extract_tts_ready_segments("  Bonjour.   Comment ça va?  ")
        assert segments == ["Bonjour."]
        assert remaining == "Comment ça va?"
