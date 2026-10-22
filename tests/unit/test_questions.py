import json
from pathlib import Path

import pytest

from app.questions import Question, QuestionFileError, display_name, load_set, scan_sets

REPO_QUESTIONS = Path(__file__).resolve().parents[2] / "questions"


def write(folder: Path, name: str, content) -> Path:
    path = folder / name
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


def test_load_set_reads_questions_in_order(tmp_path):
    path = write(tmp_path, "s.json", [
        {"question": "Q1?", "answer": "A1"},
        {"question": "Q2?", "answer": "A2"},
    ])
    assert load_set(path) == [Question("Q1?", "A1"), Question("Q2?", "A2")]


def test_load_set_trims_whitespace_and_ignores_extra_keys(tmp_path):
    path = write(tmp_path, "s.json", [{"question": "  Q?  ", "answer": "\tA\n", "category": "misc"}])
    assert load_set(path) == [Question("Q?", "A")]


def test_load_set_keeps_punctuation_and_unicode(tmp_path):
    entry = {"question": 'Who said "veni, vidi, vici": Caesar?', "answer": "Jules César"}
    path = write(tmp_path, "s.json", [entry])
    assert load_set(path) == [Question(entry["question"], entry["answer"])]


@pytest.mark.parametrize("content, message", [
    ("not json", "s.json: invalid JSON"),
    ("", "s.json: invalid JSON"),
    ('[{"question": "Q?", "answer": "A"},]', "s.json: invalid JSON"),
    ({"question": "Q?", "answer": "A"}, "s.json: must be a list"),
    ('"just a string"', "s.json: must be a list"),
    ([], "s.json: has no questions"),
    (["Q?"], "s.json entry 1: must be an object"),
    ([{"question": "Q?", "answer": "A"}, ["Q", "A"]], "s.json entry 2: must be an object"),
    ([{"answer": "A"}], 's.json entry 1: "question" must be a non-empty string'),
    ([{"question": "Q?"}], 's.json entry 1: "answer" must be a non-empty string'),
    ([{"question": "Q?", "answer": "A"}, {"question": "Q2?", "answer": "  "}],
     's.json entry 2: "answer" must be a non-empty string'),
    ([{"question": "", "answer": "A"}], 's.json entry 1: "question" must be a non-empty string'),
    ([{"question": 42, "answer": "A"}], 's.json entry 1: "question" must be a non-empty string'),
    ([{"question": "Q?", "answer": None}], 's.json entry 1: "answer" must be a non-empty string'),
    ([{"question": "Q?", "answer": 8}], 's.json entry 1: "answer" must be a non-empty string'),
], ids=repr)
def test_load_set_rejects_bad_files(tmp_path, content, message):
    path = write(tmp_path, "s.json", content)
    with pytest.raises(QuestionFileError) as exc:
        load_set(path)
    assert str(exc.value).startswith(message)


def test_load_set_rejects_missing_file(tmp_path):
    with pytest.raises(QuestionFileError, match="couldn't be read"):
        load_set(tmp_path / "missing.json")


def test_load_set_rejects_non_utf8(tmp_path):
    path = tmp_path / "s.json"
    path.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(QuestionFileError):
        load_set(path)


@pytest.mark.parametrize("set_id, name", [
    ("world-capitals", "World Capitals"),
    ("science", "Science"),
    ("movie_quotes", "Movie Quotes"),
    ("80s-music", "80s Music"),
    ("US-history", "US History"),
])
def test_display_name(set_id, name):
    assert display_name(set_id) == name


def test_scan_sets_lists_good_and_broken_sorted(tmp_path):
    write(tmp_path, "science.json", [{"question": "Q?", "answer": "A"}])
    write(tmp_path, "broken.json", "{")
    write(tmp_path, "art-history.json", [{"question": "Q?", "answer": "A"}, {"question": "Q2?", "answer": "A2"}])

    sets = scan_sets(tmp_path)

    assert [s.id for s in sets] == ["art-history", "broken", "science"]
    art, broken, science = sets
    assert art.name == "Art History" and len(art.questions) == 2 and art.error is None
    assert broken.questions == () and broken.error.startswith("broken.json: invalid JSON")
    assert len(science.questions) == 1


def test_scan_sets_ignores_other_files_and_folders(tmp_path):
    write(tmp_path, "notes.txt", "not a set")
    write(tmp_path, "set.json.bak", "[]")
    (tmp_path / "folder.json").mkdir()
    write(tmp_path, "real.json", [{"question": "Q?", "answer": "A"}])

    assert [s.id for s in scan_sets(tmp_path)] == ["real"]


def test_scan_sets_empty_folder(tmp_path):
    assert scan_sets(tmp_path) == []


def test_scan_sets_missing_folder(tmp_path):
    assert scan_sets(tmp_path / "nope") == []


def test_repo_question_sets_are_all_valid():
    # fails CI if someone commits a broken set to questions/
    sets = scan_sets(REPO_QUESTIONS)
    assert sets, "questions/ should ship with at least one set"
    for question_set in sets:
        assert question_set.error is None, question_set.error
        assert question_set.questions
