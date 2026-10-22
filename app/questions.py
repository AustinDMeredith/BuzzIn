import json
from dataclasses import dataclass
from pathlib import Path


class QuestionFileError(Exception):
    """A question set file that can't be used, with a message saying what's wrong and where."""


@dataclass(frozen=True)
class Question:
    question: str
    answer: str


@dataclass(frozen=True)
class QuestionSet:
    id: str
    name: str
    questions: tuple[Question, ...] = ()
    error: str | None = None


def display_name(set_id: str) -> str:
    """world-capitals -> World Capitals (only first letters change, so 80s-music -> 80s Music)"""
    words = set_id.replace("-", " ").replace("_", " ").split()
    return " ".join(word[:1].upper() + word[1:] for word in words) or set_id


def load_set(path: Path) -> list[Question]:
    """Read one set: a JSON list of {"question": ..., "answer": ...} objects."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QuestionFileError(f"{path.name}: invalid JSON ({exc.msg} on line {exc.lineno})") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise QuestionFileError(f"{path.name}: couldn't be read ({exc})") from exc

    if not isinstance(data, list):
        raise QuestionFileError(f'{path.name}: must be a list of {{"question": ..., "answer": ...}} objects')
    if not data:
        raise QuestionFileError(f"{path.name}: has no questions")

    questions = []
    for number, entry in enumerate(data, start=1):
        if not isinstance(entry, dict):
            raise QuestionFileError(f"{path.name} entry {number}: must be an object")
        for key in ("question", "answer"):
            value = entry.get(key)
            if not isinstance(value, str) or not value.strip():
                raise QuestionFileError(f'{path.name} entry {number}: "{key}" must be a non-empty string')
        questions.append(Question(entry["question"].strip(), entry["answer"].strip()))
    return questions


def scan_sets(directory: str | Path) -> list[QuestionSet]:
    """Every *.json file in the folder, sorted; broken files are listed with their error."""
    folder = Path(directory)
    if not folder.is_dir():
        return []
    sets = []
    for path in sorted(folder.glob("*.json")):
        if not path.is_file():
            continue
        try:
            questions = tuple(load_set(path))
        except QuestionFileError as exc:
            sets.append(QuestionSet(path.stem, display_name(path.stem), error=str(exc)))
        else:
            sets.append(QuestionSet(path.stem, display_name(path.stem), questions))
    return sets
