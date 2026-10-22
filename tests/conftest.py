import json

import pytest

from app import main
from tests.helpers import TEST_QUESTIONS, TEST_SET


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def questions_dir(tmp_path):
    """A questions folder holding just the test set; tests can drop more files in."""
    folder = tmp_path / "questions"
    folder.mkdir()
    (folder / "test-set.json").write_text(json.dumps(TEST_QUESTIONS))
    return folder


@pytest.fixture(autouse=True)
def fresh_state(questions_dir, monkeypatch):
    """Every test starts with an empty game (test set loaded), no connections, and its own questions folder."""
    monkeypatch.setattr(main, "QUESTIONS_DIR", str(questions_dir))
    monkeypatch.setattr(main, "question_sets", [TEST_SET])
    monkeypatch.setattr(main, "question_error", None)
    main.game.__init__(TEST_SET)
    main.manager.__init__()
    yield
