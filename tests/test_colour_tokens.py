"""Every intended colour pair passes WCAG contrast, in both themes.

The tokens are read out of App.vue, the one place colour is defined, so this
fails when a token changes to something that no longer passes. It checks
the pairs the stylesheet is meant to use; it cannot see a component that
uses a pair not listed here, which is what review is for.
"""

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "web" / "src" / "App.vue"

TEXT, BOUNDARY = 4.5, 3.0
PAIRS = [
    ("fg", "bg", TEXT),
    ("muted", "bg", TEXT),
    ("accent", "bg", TEXT),
    ("link", "bg", TEXT),
    ("link", "surface", TEXT),
    ("fg", "surface", TEXT),  # the home page's band
    ("muted", "surface", TEXT),
    ("fg", "chip", TEXT),  # chosen ingredients
    ("muted", "chip", TEXT),  # a choice's detail, under the pointer (OptionList)
    ("fg", "admin-bg", TEXT),
    ("fg", "ok-bg", TEXT),  # a line's check that's fine
    ("error", "surface", TEXT),  # a failed save, in the save band
    ("on-accent", "accent", TEXT),  # button text
    ("on-accent", "accent-hover", TEXT),
    ("error", "bg", TEXT),
    ("border", "bg", BOUNDARY),  # input edges
    ("accent", "bg", BOUNDARY),  # button edges
    ("focus", "bg", BOUNDARY),  # the keyboard focus ring
    ("notice-fg", "notice-bg", TEXT),  # the band saying this isn't production
]


def _tokens() -> dict[str, dict[str, str]]:
    css = APP.read_text(encoding="utf-8")
    light = re.search(r":root\s*\{(.*?)\}", css, re.S)
    # Dark is chosen by data-theme on <html> (theme.ts), set from the device
    # unless someone picks.
    dark = re.search(r':root\[data-theme="dark"\]\s*\{(.*?)\}', css, re.S)
    assert light and dark, "App.vue no longer defines both themes"

    def parse(block: str) -> dict[str, str]:
        return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", block))

    tokens = {"light": parse(light.group(1)), "dark": parse(dark.group(1))}
    assert tokens["light"].keys() == tokens["dark"].keys(), "a token is missing from one theme"
    return tokens


def _luminance(hex_colour: str) -> float:
    channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_the_formula_matches_known_values() -> None:
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("fg, bg, minimum", PAIRS)
def test_pair_passes(theme, fg, bg, minimum) -> None:
    colours = _tokens()[theme]
    ratio = contrast(colours[fg], colours[bg])
    assert ratio >= minimum, f"{theme}: --{fg} on --{bg} is {ratio:.2f}:1, needs {minimum}:1"
