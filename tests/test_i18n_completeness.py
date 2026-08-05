"""The translation table must stay complete and consistent.

Every one of these was a real defect found by auditing the table by hand:
a key used in code but never defined rendered the raw key as a button label,
a status message was borrowed as a button caption, and the whole pipeline logged
in English into a Turkish log box. A missing translation is invisible until
someone switches language, so it is checked here instead.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from audio_sync.i18n import TRANSLATIONS, Language, get_i18n, t

PACKAGE = Path(__file__).resolve().parent.parent / "audio_sync"
LANGUAGES = tuple(language.code for language in Language)


def source_files() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def literal_keys() -> set[str]:
    """Keys passed to ``t()`` as a plain string."""
    found: set[str] = set()
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "t"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                found.add(node.args[0].value)
    return found


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_key_has_every_language(language: str) -> None:
    missing = sorted(key for key, value in TRANSLATIONS.items() if not value.get(language))
    assert not missing, f"{language} çevirisi eksik: {missing}"


def test_every_key_used_in_code_exists() -> None:
    """A missing key renders as the key itself — a button once read 'cancel'."""
    undefined = sorted(literal_keys() - set(TRANSLATIONS))
    assert not undefined, f"kodda kullanılıp tabloda olmayan: {undefined}"


def test_placeholders_match_across_languages() -> None:
    """A field present in one language and not the other raises at format time."""
    def fields(text: str) -> set[str]:
        return set(re.findall(r"\{(\w+)", text))

    mismatched = {
        key: {language: sorted(fields(value[language])) for language in LANGUAGES}
        for key, value in TRANSLATIONS.items()
        if len({frozenset(fields(value[language])) for language in LANGUAGES}) > 1
    }
    assert not mismatched, f"yer tutucular uyuşmuyor: {mismatched}"


def test_every_translation_actually_formats() -> None:
    """Catches a stray brace that would blow up only on the language nobody tests."""
    for key, value in TRANSLATIONS.items():
        for language in LANGUAGES:
            text = value[language]
            names = set(re.findall(r"\{(\w+)", text))
            try:
                text.format(**{name: 0 for name in names})
            except (ValueError, IndexError, KeyError) as exc:
                pytest.fail(f"{key}[{language}] biçimlendirilemiyor: {exc}")


def test_no_user_facing_string_bypasses_the_table() -> None:
    """A hard-coded message shows through in whichever language it is not in.

    Both directions have happened here: the pipeline logged English into a
    Turkish log box, and deew's progress said "Deew komutu:" in the English one.
    So this looks at everything that reaches the user — widget captions, dialog
    messages, and anything handed to a log or progress callback.
    """
    literal = r'"([A-Za-zÇĞİÖŞÜçğıöşü][^"]{8,})"'
    patterns = [
        re.compile(rf"(?:text|message)\s*=\s*f?{literal}"),
        re.compile(rf"(?:progress_callback|log|self\._log)\(\s*f?{literal}"),
    ]
    # Prefixes that label another tool's own output. The line they carry is
    # whatever deew printed, so translating the tag would be misleading rather
    # than helpful — it names the source, it is not a message of ours.
    allowed = {"deew: {line}", "deew stderr: {line}"}

    offenders: list[str] = []
    for path in source_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "t(" in line:
                continue
            for pattern in patterns:
                match = pattern.search(line)
                if match and match.group(1) not in allowed:
                    offenders.append(f"{path.name}:{number}: {match.group(1)!r}")
                    break
    assert not offenders, f"çeviri tablosunu atlayan metin: {offenders}"


def test_the_pipeline_speaks_the_selected_language() -> None:
    """The pipeline logs into the same box as the UI, so it must follow it."""
    i18n = get_i18n()
    original = i18n.language
    try:
        i18n.set_language(Language.TR)
        turkish = t("pipe_analyzing")
        i18n.set_language(Language.EN)
        english = t("pipe_analyzing")
    finally:
        i18n.set_language(original)

    assert turkish != english
    assert turkish == "Gecikme analiz ediliyor…"
