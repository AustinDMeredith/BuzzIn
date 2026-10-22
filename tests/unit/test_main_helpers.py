import pytest

from app.main import clean_text


@pytest.mark.parametrize("value, expected", [
    ("alice", "alice"),
    ("  alice  ", "alice"),
    ("", ""),
    ("   ", ""),
    (None, ""),
    (123, "123"),
    ("abcdefgh", "abcde"),
    ("  abcdefgh", "abcde"),
])
def test_clean_text(value, expected):
    assert clean_text(value, 5) == expected
