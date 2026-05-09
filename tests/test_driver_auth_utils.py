from services.driver_auth_utils import extract_driver_serial_from_transcript


def test_extract_driver_serial_from_digits():
    assert extract_driver_serial_from_transcript("driver number 00123") == "00123"


def test_extract_driver_serial_from_english_words():
    assert extract_driver_serial_from_transcript("zero zero one two three") == "00123"


def test_extract_driver_serial_from_french_words():
    assert extract_driver_serial_from_transcript("zéro zéro un deux trois") == "00123"


def test_extract_driver_serial_returns_none_without_digits():
    assert extract_driver_serial_from_transcript("hello driver") is None
