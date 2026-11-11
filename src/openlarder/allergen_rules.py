"""Suggesting allergens from ingredients' names, for a moderator to accept
or dismiss in the Suggestions queue (kind 'allergen').

*SCOPING.md, Allergen seeding:* a first pass per ingredient, reviewed
before use. These are word rules, run by an administrator from Suggestions:
an ingredient whose name, or its FoodData Central food's description, says
"butter" may contain milk; "peanut butter", "cocoa butter" and "butter
beans" don't. n8n can add its own suggestions to the same queue (Workflow
5, SCOPING.md), reading public_ingredients and public_ingredient_allergens.

Nothing is suggested for an ingredient that records anything about that
allergen already, or inherits it from a broader one; nor for one whose
broader ingredient gets the same suggestion, as accepting that covers
both; nor where the same suggestion was decided before.
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder import allergens, visibility
from openlarder.models import FdcFood, Ingredient, Suggestion

MODEL = "rules"
VERSION = "allergen-rules-v1"

# Words that say an ingredient isn't the real thing, whatever else it says:
# "vegan butter", "egg replacer", "gluten-free flour" (but not "free-range
# eggs", nor "fat-free milk").
NOT_IT = {
    "vegan", "imitation", "substitute", "replacer", "alternative", "nondairy", "plant",
    "dairyless", "eggless", "non_dairy", "dairy_free", "gluten_free", "egg_free", "nut_free",
    "wheat_free", "soy_free", "milk_free", "allergen_free",
}  # fmt: skip


@dataclass(frozen=True)
class Rule:
    allergen: str
    status: str
    # Words, or two-word phrases, that say it.
    words: frozenset[str]
    # Words that say this one isn't ("peanut" in "peanut butter").
    unless: frozenset[str] = frozenset()
    # Said outright ("butter"), or only usually ("worcestershire").
    likely: bool = True


def _rule(allergen, words, unless=(), status="contains", likely=True) -> Rule:
    return Rule(allergen, status, frozenset(words.split()), frozenset(unless), likely)


_NOT_DAIRY = (
    "peanut almond cashew hazelnut pistachio walnut pecan macadamia nut seed sunflower"
    " pumpkin apple pear plum cocoa cacao shea coconut oat soy soya rice hemp tahini"
    " tartar bean lettuce squash mushroom"
).split()

_FLOUR_NOT_WHEAT = (
    "almond rice coconut chickpea corn cornflour tapioca oat buckwheat potato cassava"
    " arrowroot sorghum teff millet quinoa banana gram besan masa soy soya chestnut"
    " hazelnut amaranth lupin pea lentil garbanzo bean squash"
).split()

RULES = [
    _rule(
        "milk",
        "milk butter buttermilk cream cheese yogurt yoghurt ghee kefir whey casein curd ricotta"
        " mozzarella parmesan parmigiano pecorino cheddar feta mascarpone paneer brie camembert"
        " gouda gruyere gruyère halloumi quark labneh custard creme crème fraiche fraîche"
        " burrata stracciatella provolone emmental fontina manchego roquefort gorgonzola"
        " stilton taleggio cotija queso half_and",
        _NOT_DAIRY,
    ),
    _rule("milk", "white_chocolate", likely=False),
    _rule(
        "egg",
        "egg yolk mayonnaise mayo meringue aioli",
        ("eggplant", "replacer"),
    ),
    _rule(
        "fish",
        "fish anchovy salmon tuna cod haddock halibut trout sardine mackerel tilapia snapper"
        " bass swordfish pollock catfish herring bonito katsuobushi dashi",
        ("shellfish",),
    ),
    _rule("fish", "worcestershire", likely=False),
    _rule("crustaceans", "shrimp prawn crab lobster crayfish langoustine krill"),
    _rule(
        "molluscs",
        "clam mussel oyster scallop squid calamari octopus snail escargot cuttlefish abalone"
        " whelk cockle",
        ("mushroom",),
    ),
    _rule(
        "tree_nuts",
        "almond cashew walnut pecan pistachio hazelnut macadamia chestnut praline marzipan"
        " frangipane",
        ("extract", "water"),
    ),
    _rule("tree_nuts", "pine_nut brazil_nut"),
    # "Nuts", "mixed nuts": which isn't said.
    _rule("tree_nuts", "nut", ("water", "pine", "brazil"), likely=False),
    _rule("peanuts", "peanut groundnut"),
    _rule(
        "wheat",
        "wheat flour semolina spelt farro durum bulgur bulghur couscous seitan panko breadcrumb"
        " bread pasta spaghetti macaroni orzo lasagna lasagne fettuccine linguine penne"
        " pita naan baguette brioche croissant phyllo filo pastry cracker wonton kamut emmer"
        " einkorn freekeh triticale farina matzo matzah",
        _FLOUR_NOT_WHEAT + ["buckwheat", "corn", "rice", "rye", "barley"],
    ),
    _rule(
        "wheat",
        "soy_sauce shoyu hoisin noodle tortilla bun",
        ("rice", "corn", "tamari"),
        likely=False,
    ),
    _rule(
        "gluten",
        "wheat flour semolina spelt farro durum bulgur bulghur couscous seitan panko breadcrumb"
        " bread pasta spaghetti macaroni orzo lasagna lasagne fettuccine linguine penne"
        " pita naan baguette brioche croissant phyllo filo pastry cracker wonton kamut emmer"
        " einkorn freekeh triticale farina matzo matzah barley rye"
        " malt",
        _FLOUR_NOT_WHEAT + ["buckwheat", "corn", "rice"],
    ),
    _rule(
        "gluten",
        "beer soy_sauce shoyu hoisin noodle bun",
        ("rice", "tamari", "corn"),
        likely=False,
    ),
    _rule("gluten", "oat oatmeal", status="may_contain", likely=False),
    _rule("soy", "soy soya tofu tempeh edamame miso tamari soybean shoyu"),
    _rule("soy", "hoisin", likely=False),
    _rule("sesame", "sesame tahini halva halvah gomasio"),
    _rule("celery", "celery celeriac"),
    _rule("mustard", "mustard"),
    _rule("lupin", "lupin lupini"),
    _rule("sulphites", "wine sherry vermouth champagne prosecco", likely=False),
]


def words(name: str) -> set[str]:
    """A name's words, singular, with its two-word phrases joined by _."""
    raw = re.sub(r"[^a-zà-ÿ]+", " ", name.lower()).split()
    out = []
    for w in raw:
        if len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us")):
            w = w[:-1]
        out.append(w)
    return set(out) | {f"{a}_{b}" for a, b in zip(out, out[1:], strict=False)}


@dataclass(frozen=True)
class Found:
    allergen: str
    status: str
    word: str
    likely: bool
    # What said it: the ingredient's name, or its FDC food's description.
    said_by: str


def read(name: str, said_by: str) -> dict[str, Found]:
    """What a name says, by allergen; "contains" over "may contain"."""
    said = words(name)
    out: dict[str, Found] = {}
    if said & NOT_IT:
        return out
    for rule in RULES:
        hit = sorted(said & rule.words)
        if not hit or said & rule.unless:
            continue
        found = Found(rule.allergen, rule.status, hit[0].replace("_", " "), rule.likely, said_by)
        before = out.get(rule.allergen)
        if before is None or (before.status == "may_contain" and found.status == "contains"):
            out[rule.allergen] = found
    return out


def _reason(found: Found, name: str) -> str:
    where = (
        "Its name" if found.said_by == "name" else f"Its FoodData Central food, “{found.said_by}”,"
    )
    if found.status == "may_contain":
        verb = "may contain"
    else:
        verb = "contains" if found.likely else "usually contains"
    return f"{where} says “{found.word}”: {name} {verb} {found.allergen.replace('_', ' ')}."


async def suggest(session: AsyncSession) -> int:
    """Add a suggestion for each public ingredient's allergens its name
    says; how many were new."""
    rows = (
        await session.execute(
            select(Ingredient.id, Ingredient.name, Ingredient.parent_id, FdcFood.description)
            .outerjoin(FdcFood, FdcFood.fdc_id == Ingredient.fdc_id)
            .where(visibility.ingredients_seen_by(None))
        )
    ).all()
    parent = {i: p for i, _, p, _ in rows}
    names = {i: n for i, n, _, _ in rows}
    said: dict[uuid.UUID, dict[str, Found]] = {}
    for i, name, _, food in rows:
        found = read(food, food) if food else {}
        # Its own name first: it's what the moderator sees.
        found.update(read(name, "name"))
        if found:
            said[i] = found
    if not said:
        return 0
    recorded = await allergens.recorded(session, list(said))
    decided = {
        (t.get("ingredient_id"), t.get("allergen"))
        for t in await session.scalars(
            select(Suggestion.target).where(
                Suggestion.kind == "allergen", Suggestion.status != "open"
            )
        )
        if isinstance(t, dict)
    }

    def broader_says(i: uuid.UUID, found: Found) -> bool:
        seen, up = set(), parent.get(i)
        while up is not None and up not in seen:
            seen.add(up)
            above = said.get(up, {}).get(found.allergen)
            if above is not None and above.status == found.status:
                return True
            up = parent.get(up)
        return False

    new = 0
    for i, found_here in said.items():
        for found in found_here.values():
            if found.allergen in recorded[i] or (str(i), found.allergen) in decided:
                continue
            if broader_says(i, found):
                continue
            result = await session.execute(
                insert(Suggestion)
                .values(
                    kind="allergen",
                    target={"ingredient_id": str(i), "allergen": found.allergen},
                    proposal={
                        "ingredient_id": str(i),
                        "ingredient_name": names[i],
                        "allergen": found.allergen,
                        "status": found.status,
                        **({"certainty": "likely"} if found.likely else {}),
                    },
                    reason=_reason(found, names[i]),
                    model=MODEL,
                    prompt_version=VERSION,
                )
                .on_conflict_do_nothing(
                    index_elements=["kind", "target"], index_where=text("status = 'open'")
                )
                .returning(Suggestion.id)
            )
            new += result.scalar() is not None
    await session.commit()
    return new
