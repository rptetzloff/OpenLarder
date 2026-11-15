"""The ingredient hierarchy is said one way: cheddar counts as cheese, and
cheese includes cheddar.

*Ray, 2026-11-15, of "Comes under": chose "Counts as".* His round 5 list
replaces the spatial words (comes under, under it, broader, narrower, top
level) everywhere a person can read them, and leaves the code's own names
(`parent_id`, `children`, `top`, `Broader`) and its comments and docstrings
as they are, to change when the code around them does.

This reads the source, so it proves the source: that no text a page, an
API answer or the data dictionary could show still has the old words. It
can't see a sentence that says the old idea in words not listed here, and
it doesn't look at what a page renders; the accessibility check
(web/a11y/check.mjs) looks at an ingredient's page for "Counts as" and
"Includes".
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# The old ways of saying it. The first ten are the list's own; the rest are
# their neighbours, found in the same pass.
OLD = re.compile(
    r"comes under|what's under|under it now|out from under|nothing broader"
    r"|nothing narrower|top level|one under another|broader ingredient"
    r"|narrower ingredient"
    r"|put (it |another ingredient )?under|add under this|go(es)? under|move it under"
    r"|belong under|broader and narrower|broader one|a broad one|no broader",
    re.IGNORECASE,
)

HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# From // to the line's end, when it starts the line or follows a space: an
# address ("https://…") has a colon before it.
LINE_COMMENT = re.compile(r"(^|\s)//.*$", re.MULTILINE)


def said_by_the_page(source: str) -> str:
    """A .vue or .ts file without its comments: what's left is code and the
    words in it."""
    return LINE_COMMENT.sub(r"\1", BLOCK_COMMENT.sub("", HTML_COMMENT.sub("", source)))


def said_by_the_server(source: str) -> list[str]:
    """Every string in a Python file that isn't a docstring."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def _old_words() -> list[str]:
    found = []
    for path in sorted((ROOT / "web" / "src").rglob("*")):
        if path.suffix in (".vue", ".ts"):
            text = said_by_the_page(path.read_text(encoding="utf-8"))
            found += [f"{path.relative_to(ROOT)}: {m.group(0)}" for m in OLD.finditer(text)]
    for path in sorted((ROOT / "src" / "openlarder").rglob("*.py")):
        for text in said_by_the_server(path.read_text(encoding="utf-8")):
            found += [f"{path.relative_to(ROOT)}: {m.group(0)}" for m in OLD.finditer(text)]
    return found


def test_nothing_a_person_reads_says_it_the_old_way() -> None:
    assert _old_words() == []


@pytest.mark.parametrize(
    "source",
    [
        "<template><h2>Comes under</h2></template>",
        '<script setup lang="ts">\nconst label = "Top level only";\n</script>',
        "<template>\n  <p>See https://example.com: put it under Ginger.</p>\n</template>",
    ],
)
def test_the_old_words_on_a_page_are_seen(source: str) -> None:
    """The control: the search finds them where a person would read them."""
    assert OLD.search(said_by_the_page(source))


@pytest.mark.parametrize(
    "source",
    [
        "<template><!-- what it comes under --><h2>Counts as</h2></template>",
        "// Broader and narrower: cheese above cheddar.\nconst a = 1;",
        "const a = 1; // top level\n",
        ".more {\n  /* what it comes under, on a line of its own */\n  display: block;\n}",
    ],
)
def test_a_comment_on_a_page_is_left_alone(source: str) -> None:
    assert not OLD.search(said_by_the_page(source))


def test_the_servers_words_are_seen_and_its_docstrings_left_alone() -> None:
    source = (
        '"""What it comes under."""\n'
        "def refuse(name):\n"
        '    """A broader ingredient."""\n'
        "    # nothing broader\n"
        '    raise ValueError(f"{name} can\'t go under itself.")\n'
    )
    said = said_by_the_server(source)
    assert [s for s in said if OLD.search(s)] == [" can't go under itself."]


def test_the_pages_say_it_the_new_way() -> None:
    """The words that replaced them are where the old ones were, so the
    test above isn't passing on pages that say nothing at all."""
    pages = ROOT / "web" / "src" / "pages"
    ingredient = said_by_the_page((pages / "IngredientPage.vue").read_text(encoding="utf-8"))
    assert "<h2>Counts as</h2>" in ingredient and "<h2>Includes</h2>" in ingredient
    listed = said_by_the_page((pages / "IngredientsPage.vue").read_text(encoding="utf-8"))
    assert "Main ingredients only" in listed and ">Counts as <a" in listed
