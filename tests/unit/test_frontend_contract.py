"""Checks that the templates and the small bits of JS agree on ids, scripts and globals."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "app" / "templates"
STATIC = ROOT / "static"


def scripts_on(page: str) -> list[Path]:
    html = (TEMPLATES / page).read_text()
    return [STATIC / src for src in re.findall(r'<script src="/static/([^"]+)"', html)]


def top_level_names(script: Path) -> list[str]:
    source = script.read_text()
    return re.findall(r"^(?:let|const|var|class|function)\s+(\w+)", source, re.M)


@pytest.mark.parametrize("page", ["index.html", "host.html"])
def test_page_scripts_exist(page):
    for script in scripts_on(page):
        assert script.is_file(), f"{page} loads missing {script}"


@pytest.mark.parametrize("page", ["index.html", "host.html"])
def test_page_scripts_do_not_redeclare_globals(page):
    # classic scripts share one global scope, so a repeated `let` is a SyntaxError
    seen: dict[str, Path] = {}
    for script in scripts_on(page):
        for name in top_level_names(script):
            assert name not in seen, f"{name} declared in both {seen[name].name} and {script.name}"
            seen[name] = script


def test_player_page_loads_its_scripts_once():
    names = [script.name for script in scripts_on("index.html")]
    assert names == ["buzz.js", "countdown.js"]


def test_host_page_loads_its_scripts_once():
    assert [script.name for script in scripts_on("host.html")] == ["countdown.js"]


PARTIALS = sorted((TEMPLATES / "partials").glob("*.html"))


def ws_send_forms(html: str) -> list[str]:
    return re.findall(r"<form[^>]*\bws-send\b.*?</form>", html, re.S)


@pytest.mark.parametrize("partial, input_id, message_type", [
    ("join.html", "player", "join"),
    ("start_game.html", "host", "host_join"),
])
def test_join_forms_send_over_websocket_on_enter(partial, input_id, message_type):
    # the submit button must live inside the ws-send form, or Enter does a normal GET submit
    html = (TEMPLATES / "partials" / partial).read_text()
    forms = ws_send_forms(html)
    assert len(forms) == 1, f"{partial} needs exactly one ws-send form"
    form = forms[0]
    assert f"hx-vals='{{\"type\": \"{message_type}\"}}'" in form
    assert f'id="{input_id}" name="{input_id}"' in form
    assert 'type="submit"' in form
    assert "onclick" not in html


# htmx reads ws-send form fields through a proxy over FormData, so a field named after a
# FormData method (e.g. "set") comes through as a function and silently vanishes from the message
FORMDATA_METHODS = {"append", "delete", "entries", "forEach", "get", "getAll", "has", "keys", "set", "values"}


@pytest.mark.parametrize("partial", PARTIALS, ids=lambda p: p.name)
def test_ws_send_field_names_do_not_shadow_formdata(partial):
    for form in ws_send_forms(partial.read_text()):
        for name in re.findall(r'\bname="([^"]+)"', form):
            assert name not in FORMDATA_METHODS, f'{partial.name}: field name="{name}" is a FormData method'


def test_ws_send_forms_exist_where_expected():
    forms = {p.name: len(ws_send_forms(p.read_text())) for p in PARTIALS}
    assert forms["join.html"] == 1
    assert forms["start_game.html"] == 1
    assert forms["host_controls.html"] == 2  # set picker + chat
    assert forms["game.html"] == 2  # answer + chat


def test_buzz_script_targets_buzz_button():
    source = (STATIC / "js" / "buzz.js").read_text()
    html = (TEMPLATES / "partials" / "game.html").read_text()
    assert 'getElementById("buzz-button")' in source
    assert 'id="buzz-button"' in html


def test_buzz_script_ignores_typing_in_inputs():
    source = (STATIC / "js" / "buzz.js").read_text()
    assert 'matches("input, textarea")' in source


@pytest.mark.parametrize("partial", ["game.html", "host_controls.html"])
def test_countdown_script_targets_countdown_elements(partial):
    source = (STATIC / "js" / "countdown.js").read_text()
    html = (TEMPLATES / "partials" / partial).read_text()
    assert '.countdown[data-seconds-left]' in source
    assert 'class="countdown" data-seconds-left=' in html
