"""One spelling in what's shown and sent: American.

*Ray's round 2 spec, 2026-11-13:* the interface mixed "Organisations" with
"Catalog". Comments and identifiers are left as they are, so this reads
only what a person can be shown: the text of each page's template, the
quoted text in the pages' scripts, and the server's strings.

It reads the source, so it proves the source. What it can't see:

- A lower-case word alone in quotes is taken for a value the code compares
  ("organisation" is how an author's kind is stored), so one that's shown
  as it is gets past.
- Text kept in the database: migration 0072 changed the one label there
  was ("Sulphites"), and test_the_sulphites_label_is_american asks the API.
- A word that isn't on the list.

Two things that aren't spelling, decided the same day (*Ray, 2026-11-13:
"check and November 13, 2026"*, asked which to use): a box is checked, not
ticked; and a date written out has its month first.
"""

import ast
import re
from pathlib import Path

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]

BRITISH = re.compile(
    r"\b\w*(?:"
    r"organis|recognis|realis|apologis|capitalis|categoris|customis|minimis|normalis|optimis|"
    r"prioritis|summaris|specialis|standardis|authoris|initialis|itemis|finalis|personalis|"
    r"utilis|visualis|generalis|alphabetis|analys(?=e|i)|catalogu|"
    r"colour|flavour|favour|honour|neighbour|behaviour|labour|"
    r"travell|cancell|modell|labell(?=ed\b|ing\b)|licenc|defenc|offenc|judgement|programme|"
    r"whilst|amongst|learnt|misspelt|sulph|aluminium|"
    r"\bgrey|\bcentre|\bmetre|\blitre|\bfibre|\btheatre"
    r")\w*",
    re.IGNORECASE,
)
# American usage, where the words are spelled the same: a box is checked, and a
# date is "November 13, 2026".
USAGE = re.compile(
    r"\b(?:un)?tick(?:ed|ing|s)?\b"
    r"|\b\d{1,2} (?:January|February|March|April|May|June|July|August|September|October"
    r"|November|December) \d{4}\b",
    re.IGNORECASE,
)
# A value, not words: lower case, alone in its quotes.
VALUE = re.compile(r"^[a-z_]+$")

# Strings that hold British spellings on purpose, by file: words the rules
# look for in ingredients' names and lines, which come in both spellings.
DATA = {
    "src/openlarder/allergen_rules.py": {"flavour", "flavoured", "flavouring"},
    "src/openlarder/detector.py": {"litres"},
    "src/openlarder/recipes.py": {"millilitres", "litres"},
    # The database's own check on an author's kind, in SQL.
    "src/openlarder/models/catalog.py": {"organisation"},
}


def _british(words: str, path: str) -> list[str]:
    spelt = [w for w in BRITISH.findall(words) if w.lower() not in DATA.get(path, ())]
    return spelt + USAGE.findall(words)


def _python_strings(path: Path) -> list[tuple[int, str]]:
    """Every string in the file that could be shown: not a docstring, unless
    it's a route's, which the API's documentation prints."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    served = "routers" in path.parts
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                routed = isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and any(
                    "router." in ast.unparse(d) for d in node.decorator_list
                )
                if not (served and routed):
                    docstrings.add(id(first.value))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


QUOTED = re.compile(r"""(["'`])((?:\\.|(?!\1).)*)\1""")
# Comments, which aren't shown. Two patterns: with DOTALL, a line comment's
# ".*$" would run to the end of the file and take the page with it.
BLOCK_COMMENT = re.compile(r"<!--.*?-->|/\*.*?\*/", re.DOTALL)
LINE_COMMENT = re.compile(r"^\s*//.*$|\s//\s.*$", re.MULTILINE)
TAG = re.compile(r"<[^>]*>", re.DOTALL)


# The code inside a template string: `/search?${ticked.value.map(...)}` has
# a name in it, not a word. To its closing brace, or the string's end where
# another template string inside cut it short.
IN_TEMPLATE_STRING = re.compile(r"\$\{[^}]*(?:\}|$)")


def _quoted(source: str) -> list[str]:
    return [IN_TEMPLATE_STRING.sub(" ", m.group(2)) for m in QUOTED.finditer(source)]


ATTRIBUTE = re.compile(r"""([:@#\w.-]+)=(?:"([^"]*)"|'([^']*)')""")
# Attributes that name things for the page's own use, not words for a person:
# a class is "larder-tick" whatever the page says.
NAMES = {
    "class", "id", "for", "href", "src", "type", "name", "role", "rel", "value", "ref", "key",
    "to", "method", "action", "autocomplete", "inputmode", "viewBox", "d", "fill", "stroke",
    "lang", "target", "scope", "loading", "width", "height", "kind", "input-id", "what",
}  # fmt: skip
WORDS_IN_ARIA = {"aria-label", "aria-description", "aria-placeholder", "aria-valuetext"}


def _page_strings(path: Path) -> list[str]:
    """What a .vue or .ts file can show: the words of its template, its
    plain attributes (a placeholder, an aria-label), and the quoted text
    inside its template's expressions and its script. An expression itself
    is code: `:href="dumps.licence_url"` shows nobody a word."""
    source = LINE_COMMENT.sub(" ", BLOCK_COMMENT.sub(" ", path.read_text(encoding="utf-8")))
    if path.suffix != ".vue":
        return _quoted(source)
    start, end = source.find("<template>"), source.rfind("</template>")
    template = source[start:end] if start != -1 else ""
    script = re.sub(r"<style.*?</style>", " ", source.replace(template, " "), flags=re.DOTALL)
    found = _quoted(script)
    for name, double, single in ATTRIBUTE.findall(template):
        value = double or single
        if name.startswith((":", "@", "#", "v-")):
            found += _quoted(value)
        elif name not in NAMES and (not name.startswith("aria-") or name in WORDS_IN_ARIA):
            found.append(value)
    for expression in re.findall(r"\{\{(.*?)\}\}", template, flags=re.DOTALL):
        found += _quoted(expression)
    found.append(TAG.sub(" ", re.sub(r"\{\{.*?\}\}", " ", template, flags=re.DOTALL)))
    return found


def _files(folder: str, *suffixes: str) -> list[Path]:
    return sorted(
        p
        for p in (ROOT / folder).rglob("*")
        if p.suffix in suffixes and "__pycache__" not in p.parts
    )


def test_nothing_the_server_sends_is_in_british_spelling() -> None:
    found = []
    for path in _files("src/openlarder", ".py"):
        name = path.relative_to(ROOT).as_posix()
        for line, string in _python_strings(path):
            if VALUE.match(string):
                continue
            found += [f"{name}:{line}: {w}" for w in _british(string, name)]
    assert found == []


def test_nothing_a_page_shows_is_in_british_spelling() -> None:
    found = []
    for path in [*_files("web/src", ".vue", ".ts"), ROOT / "web" / "index.html"]:
        name = path.relative_to(ROOT).as_posix()
        for string in _page_strings(path):
            if VALUE.match(string):
                continue
            found += [f"{name}: {w}" for w in _british(string, name)]
    assert found == []


@pytest.mark.parametrize(
    "words, caught",
    [
        ("People and organisations credited on sources.", ["organisations"]),
        ("Organisation", ["Organisation"]),
        ("checked and greyed", ["greyed"]),
        ("the same licence", ["licence"]),
        ("how OpenLarder recognises you", ["recognises"]),
        ("the misspelt ingredient", ["misspelt"]),
        ("Sulphites", ["Sulphites"]),
        # And what it leaves: the same in both spellings, or American already.
        ("Organizations, license, recognizes, gray, catalog, color, sulfites", []),
        ("promise otherwise precise advertise exercise your flour hour reference", []),
        ('aria-labelledby="x"', []),
        ("labelled as its book has it", ["labelled"]),
        # Usage: checked, not ticked; the month first.
        ("Tick a list to search with what's on it.", ["Tick"]),
        ("2 things ticked. Untick one.", ["ticked", "Untick"]),
        ("Last updated 13 November 2026", ["13 November 2026"]),
        ("Last updated November 13, 2026; a ticket, a stick, 13 Novembers", []),
    ],
)
def test_the_list_catches_what_it_should(words, caught) -> None:
    assert _british(words, "") == caught


def test_a_value_isnt_taken_for_words() -> None:
    assert VALUE.match("organisation") and VALUE.match("sulphites")
    assert not VALUE.match("Organisation") and not VALUE.match("an organisation")


async def test_the_sulphites_label_is_american(client, adb) -> None:
    """The one label the database held in British spelling (migration 0072).
    Its key is as it was: the API and the dumps name it by that."""
    assert (
        await adb.scalar(text("SELECT label FROM allergens WHERE key = 'sulphites'")) == "Sulfites"
    )
    labels = [label for (label,) in await adb.execute(text("SELECT label FROM allergens"))] + [
        name for (name,) in await adb.execute(text("SELECT name FROM tags"))
    ]
    assert [w for label in labels for w in _british(label, "")] == []
