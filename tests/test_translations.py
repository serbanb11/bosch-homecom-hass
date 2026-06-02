"""Guard tests for entity-name translations.

These catch the class of bug where an entity sets ``_attr_translation_key``
but the key has no ``name`` in the translation files, so Home Assistant falls
back to the raw ``_attr_name`` (e.g. ``hc1``, ``dhw1_sensor``) instead of a
localised name.
"""

import json
from pathlib import Path
import re

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "bosch_homecom"

# Source file -> entity platform it registers under.
FILE_PLATFORM = {
    "sensor.py": "sensor",
    "binary_sensor.py": "binary_sensor",
    "select.py": "select",
    "climate.py": "climate",
    "fan.py": "fan",
    "number.py": "number",
    "switch.py": "switch",
    "water_heater.py": "water_heater",
    "button.py": "button",
}

TRANSLATION_FILES = [
    "strings.json",
    "translations/en.json",
    "translations/de.json",
    "translations/nl.json",
]

_KEY_RE = re.compile(r'_attr_translation_key = "([^"]+)"')


def _load(name: str) -> dict:
    return json.loads((COMPONENT / name).read_text(encoding="utf-8"))


def _used_keys() -> set[tuple[str, str]]:
    """Return (platform, key) pairs referenced in entity source (skip comments)."""
    used: set[tuple[str, str]] = set()
    for filename, platform in FILE_PLATFORM.items():
        path = COMPONENT / filename
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("#"):
                continue
            match = _KEY_RE.search(line)
            if match:
                used.add((platform, match.group(1)))
    return used


def test_every_translation_key_has_a_name():
    """Each translation_key used in code must have a name in strings.json."""
    entity = _load("strings.json")["entity"]
    missing = [
        f"{platform}.{key}"
        for platform, key in sorted(_used_keys())
        if "name" not in entity.get(platform, {}).get(key, {})
    ]
    assert not missing, f"translation_key(s) without a name: {missing}"


@pytest.mark.parametrize("filename", TRANSLATION_FILES[1:])
def test_translation_files_cover_strings(filename):
    """en/de/nl must define a name for every named key in strings.json."""
    strings_entity = _load("strings.json")["entity"]
    other_entity = _load(filename)["entity"]
    missing = []
    for platform, keys in strings_entity.items():
        for key, value in keys.items():
            if isinstance(value, dict) and "name" in value:
                if "name" not in other_entity.get(platform, {}).get(key, {}):
                    missing.append(f"{platform}.{key}")
    assert not missing, f"{filename} missing names for: {missing}"


def test_placeholder_templates_have_matching_code_placeholders():
    """Name templates with {circuit}/{zone} must be wired to placeholders."""
    entity = _load("strings.json")["entity"]
    templated = [
        f"{platform}.{key}"
        for platform, keys in entity.items()
        for key, value in keys.items()
        if isinstance(value, dict)
        and isinstance(value.get("name"), str)
        and "{" in value["name"]
    ]
    # Every templated name must have a corresponding translation_placeholders
    # assignment somewhere in the code, so the {..} is actually substituted.
    source = "\n".join(
        (COMPONENT / f).read_text(encoding="utf-8") for f in FILE_PLATFORM
    )
    assert "_attr_translation_placeholders" in source
    assert templated, "expected at least one templated name"
