"""Equipment: what a recipe can't be made without, and a list to start from.

*Decided by Ray, 2026-11-15 (his spec is in private/):* equipment is
recorded the way ingredients are, with a list of expected things left off.
A blender, a food processor, a stand mixer and a Dutch oven are recorded,
not assumed; shaped pans are recorded and plain ones assumed.

The tables (models/equipment.py):

- equipment: one thing, with `assumed` for what any kitchen has. An assumed
  thing is in the list and never on a recipe.
- equipment_aliases: its other names, as ingredient_aliases.
- equipment_counts_as: one thing counting as another. A table, where an
  ingredient has a parent column, because a multicooker counts as a
  pressure cooker and as a slow cooker (*Ray, 2026-11-15: several*).
- recipe_equipment and equipment_options: a recipe's needs and what meets
  each, as recipe_ingredients and ingredient_options. Nothing writes to
  them yet: the recipe form's field comes next.
- recipes.equipment_checked: whether anyone has said what a recipe needs.
  False for every recipe there is, which is "not recorded yet", never
  "nothing special".

The list below starts from the spec's and isn't held to it (*Ray,
2026-11-15: "why would we limit it to things in the sample listing?"*).
What was added and changed is Claude's choice, the same day, for
moderators to correct from the site once its tools are there:

- A name that offered two things is one name and another name for it:
  "Spice grinder", also called "Coffee grinder". Typed into a recipe, "A or
  B" will mean a need with two options, so no name may hold an "or".
- "Mixer", "Thermometer" and "Steamer" are there for what counts as them:
  the spec's rule is that a stand mixer covers a recipe that needs a mixer.
- "Baking stone" is another name for "Pizza stone", not a second thing.
- A few dozen things the spec didn't list (a salad spinner, a pizza peel).

The spec's groups (appliances, bakeware and so on) aren't stored: they were
a way to lay the list out, not part of the design (*Ray, 2026-11-15*).

Nothing here is in the edit history: seeds aren't edits. Its triggers come
with the tools that change these rows.

Revision ID: 0079
Revises: 0078
"""

import re
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0079"
down_revision: str | None = "0078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Expected in any kitchen: (name, other names).
ASSUMED = [
    ("Knife", ["Chef's knife", "Paring knife"]),
    ("Cutting board", ["Chopping board"]),
    ("Mixing bowl", ["Bowl"]),
    ("Saucepan", []),
    ("Stockpot", ["Stock pot", "Soup pot"]),
    ("Skillet", ["Frying pan", "Fry pan"]),
    ("Baking sheet", ["Sheet pan", "Cookie sheet", "Baking tray"]),
    ("Baking dish", ["Casserole dish"]),
    ("Oven", []),
    ("Stovetop", ["Stove", "Hob"]),
    ("Microwave", ["Microwave oven"]),
    ("Refrigerator", ["Fridge"]),
    ("Freezer", []),
    ("Measuring cups and spoons", ["Measuring cups", "Measuring spoons", "Measuring jug"]),
    ("Wooden spoon", []),
    ("Spatula", ["Rubber spatula", "Turner"]),
    ("Whisk", []),
    ("Tongs", []),
    ("Ladle", []),
    ("Colander", []),
    ("Sieve", ["Fine-mesh strainer", "Fine-mesh sieve", "Strainer"]),
    ("Grater", ["Box grater"]),
    ("Vegetable peeler", ["Peeler"]),
    ("Can opener", ["Tin opener"]),
    ("Rolling pin", []),
    ("Cooling rack", ["Wire rack"]),
    ("Parchment paper", ["Baking paper", "Baking parchment"]),
    ("Foil", ["Aluminum foil", "Tin foil"]),
    ("Plastic wrap", ["Cling film"]),
    ("Kitchen towel", ["Tea towel", "Dish towel"]),
    ("Oven mitts", ["Oven gloves", "Pot holders"]),
    ("Timer", ["Kitchen timer"]),
]

# Recorded on a recipe that needs one: (name, other names, what it counts as).
RECORDED = [
    # Appliances
    ("Mixer", ["Electric mixer"], []),
    ("Stand mixer", [], ["Mixer"]),
    ("Hand mixer", [], ["Mixer"]),
    ("Blender", [], []),
    ("High-speed blender", [], ["Blender"]),
    ("Immersion blender", ["Stick blender", "Hand blender"], []),
    ("Food processor", [], []),
    ("Spice grinder", ["Coffee grinder"], []),
    ("Pressure cooker", [], []),
    ("Slow cooker", [], []),
    (
        "Multicooker",
        ["Instant Pot", "Electric pressure cooker"],
        ["Pressure cooker", "Slow cooker"],
    ),
    ("Rice cooker", [], []),
    ("Air fryer", [], []),
    ("Deep fryer", [], []),
    ("Bread machine", ["Bread maker"], []),
    ("Ice cream maker", ["Ice cream machine"], []),
    ("Waffle iron", ["Waffle maker"], []),
    ("Sous vide circulator", ["Immersion circulator", "Sous vide machine"], []),
    ("Dehydrator", ["Food dehydrator"], []),
    ("Juicer", [], []),
    ("Grain mill", ["Flour mill"], []),
    ("Vacuum sealer", [], []),
    ("Kitchen torch", ["Blowtorch", "Culinary torch"], []),
    ("Toaster oven", [], []),
    ("Panini press", ["Sandwich press"], []),
    # Outdoors
    ("Grill", ["Barbecue"], []),
    ("Charcoal grill", [], ["Grill"]),
    ("Gas grill", [], ["Grill"]),
    ("Smoker", [], []),
    ("Pizza oven", [], []),
    # Pots and pans
    ("Dutch oven", [], []),
    ("Cast-iron skillet", ["Cast-iron pan"], []),
    ("Wok", [], []),
    ("Grill pan", ["Griddle pan"], []),
    ("Griddle", [], []),
    ("Roasting pan with rack", ["Roasting rack"], []),
    ("Steamer", [], []),
    ("Steamer basket", [], ["Steamer"]),
    ("Bamboo steamer", [], ["Steamer"]),
    ("Double boiler", ["Bain-marie"], []),
    ("Tagine", [], []),
    ("Paella pan", [], []),
    ("Crepe pan", [], []),
    ("Fondue pot", [], []),
    ("Clay pot", [], []),
    # Shaped bakeware
    ("Springform pan", ["Springform tin"], []),
    ("Bundt pan", [], []),
    ("Tube pan", ["Angel food cake pan"], []),
    ("Loaf pan", ["Loaf tin"], []),
    ("Muffin tin", ["Muffin pan", "Cupcake pan"], []),
    ("Mini muffin tin", ["Mini muffin pan"], []),
    ("Tart pan", ["Tart pan with removable bottom", "Tart tin"], []),
    ("Pie plate", ["Pie dish", "Pie pan", "Pie tin"], []),
    ("Ramekins", [], []),
    ("Madeleine pan", [], []),
    ("Donut pan", ["Doughnut pan"], []),
    ("Popover pan", [], []),
    ("Round cake pan", ["Cake pan", "Cake tin"], []),
    ("Jelly roll pan", ["Swiss roll tin"], []),
    ("Soufflé dish", [], []),
    ("Pudding basin", [], []),
    ("Pizza stone", ["Baking stone", "Pizza steel", "Baking steel"], []),
    ("Pizza peel", [], []),
    ("Pie weights", ["Baking beans"], []),
    ("Silicone baking mat", [], []),
    # Tools
    ("Kitchen scale", ["Scale", "Digital scale"], []),
    ("Thermometer", [], []),
    ("Instant-read thermometer", ["Meat thermometer", "Probe thermometer"], ["Thermometer"]),
    ("Candy thermometer", ["Deep-fry thermometer", "Sugar thermometer"], ["Thermometer"]),
    ("Pasta machine", ["Pasta roller", "Pasta maker"], []),
    ("Pasta extruder", [], []),
    ("Mandoline", [], []),
    ("Mortar and pestle", ["Pestle and mortar"], []),
    ("Molcajete", [], ["Mortar and pestle"]),
    ("Food mill", [], []),
    ("Potato ricer", ["Ricer"], []),
    ("Piping bag", ["Pastry bag", "Piping bag and tips"], []),
    ("Pastry cutter", ["Pastry blender"], []),
    ("Pastry brush", [], []),
    ("Bench scraper", ["Dough scraper"], []),
    ("Offset spatula", [], []),
    ("Cookie cutters", [], []),
    ("Biscuit cutter", [], []),
    ("Tortilla press", [], []),
    ("Spiralizer", [], []),
    ("Zester", ["Rasp grater"], []),
    ("Citrus juicer", ["Citrus reamer"], []),
    ("Garlic press", [], []),
    ("Salad spinner", [], []),
    ("Meat mallet", ["Meat tenderizer"], []),
    ("Kitchen twine", ["Butcher's twine"], []),
    ("Cheesecloth", ["Muslin"], []),
    ("Nut milk bag", [], []),
    ("Fat separator", [], []),
    ("Funnel", [], []),
    ("Meat grinder", ["Mincer"], []),
    ("Sausage stuffer", [], []),
    ("Canning pot", ["Water bath canner", "Canning pot and jars", "Canning jars"], []),
    ("Pressure canner", [], []),
    ("Fermentation crock", [], []),
    ("Fermentation weights", ["Fermentation weights and airlock", "Airlock"], []),
    ("Banneton", ["Proofing basket"], []),
    ("Lame", ["Bread lame"], []),
    ("Sushi mat", ["Bamboo mat"], []),
    ("Popsicle molds", ["Ice pop molds"], []),
    ("Cocktail shaker", [], []),
    ("Muddler", [], []),
    ("Skewers", [], []),
]


def _stem(word: str) -> str:
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    if len(word) > 3 and word.endswith("y"):
        word = word[:-1] + "i"
    return word


def match_key(name: str) -> str:
    """ingredients.match_key as it was on 2026-11-15. Its own copy: a later
    change to the app's mustn't change what this migration wrote."""
    words = re.findall(r"[^\W_]+", name.casefold().replace("&", " and "))
    return " ".join(_stem(w) for w in words)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _id() -> sa.Column:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


TIMESTAMPED = ("equipment", "equipment_aliases", "recipe_equipment", "equipment_options")


def upgrade() -> None:
    equipment = op.create_table(
        "equipment",
        _id(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("match_key", sa.Text(), nullable=False),
        sa.Column("assumed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("shopping_term", sa.Text(), nullable=True),
        sa.Column("wikidata_id", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("name <> ''", name=op.f("ck_equipment_name_not_empty")),
        sa.CheckConstraint("match_key <> ''", name=op.f("ck_equipment_match_key_not_empty")),
        sa.CheckConstraint(
            "shopping_term <> ''", name=op.f("ck_equipment_shopping_term_not_empty")
        ),
        sa.CheckConstraint(
            "wikidata_id ~ '^Q[1-9][0-9]*$'", name=op.f("ck_equipment_wikidata_id_format")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment")),
        sa.UniqueConstraint("match_key", name=op.f("uq_equipment_match_key")),
    )
    op.create_index("uq_equipment_name", "equipment", [sa.text("lower(name)")], unique=True)

    aliases = op.create_table(
        "equipment_aliases",
        _id(),
        sa.Column("equipment_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("match_key", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("name <> ''", name=op.f("ck_equipment_aliases_name_not_empty")),
        sa.CheckConstraint(
            "match_key <> ''", name=op.f("ck_equipment_aliases_match_key_not_empty")
        ),
        sa.CheckConstraint(
            "region IN ('US', 'UK', 'AU')", name=op.f("ck_equipment_aliases_region_known")
        ),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["equipment.id"],
            name=op.f("fk_equipment_aliases_equipment_id_equipment"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_aliases")),
    )
    op.create_index(
        "uq_equipment_aliases_name_region",
        "equipment_aliases",
        [sa.text("lower(name)"), "region"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(
        "uq_equipment_aliases_match_key",
        "equipment_aliases",
        ["match_key"],
        unique=True,
        postgresql_where=sa.text("region IS NULL"),
    )
    op.create_index("ix_equipment_aliases_equipment_id", "equipment_aliases", ["equipment_id"])

    counts_as = op.create_table(
        "equipment_counts_as",
        sa.Column("equipment_id", sa.UUID(), nullable=False),
        sa.Column("counts_as_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "equipment_id <> counts_as_id", name=op.f("ck_equipment_counts_as_not_itself")
        ),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["equipment.id"],
            name=op.f("fk_equipment_counts_as_equipment_id_equipment"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["counts_as_id"],
            ["equipment.id"],
            name=op.f("fk_equipment_counts_as_counts_as_id_equipment"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "equipment_id", "counts_as_id", name=op.f("pk_equipment_counts_as")
        ),
    )
    op.create_index("ix_equipment_counts_as_counts_as_id", "equipment_counts_as", ["counts_as_id"])

    op.create_table(
        "recipe_equipment",
        _id(),
        sa.Column("recipe_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("detail <> ''", name=op.f("ck_recipe_equipment_detail_not_empty")),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_equipment_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe_equipment")),
        sa.UniqueConstraint(
            "recipe_id", "position", name=op.f("uq_recipe_equipment_recipe_id_position")
        ),
        sa.UniqueConstraint("recipe_id", "id", name=op.f("uq_recipe_equipment_recipe_id_id")),
    )
    op.create_table(
        "equipment_options",
        _id(),
        sa.Column("recipe_equipment_id", sa.UUID(), nullable=False),
        sa.Column("recipe_id", sa.UUID(), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("equipment_id", sa.UUID(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("rank >= 1", name=op.f("ck_equipment_options_rank_positive")),
        sa.ForeignKeyConstraint(
            ["recipe_id", "recipe_equipment_id"],
            ["recipe_equipment.recipe_id", "recipe_equipment.id"],
            name="fk_equipment_options_need",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["equipment.id"],
            name=op.f("fk_equipment_options_equipment_id_equipment"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment_options")),
        sa.UniqueConstraint(
            "recipe_equipment_id",
            "rank",
            name=op.f("uq_equipment_options_recipe_equipment_id_rank"),
        ),
        sa.UniqueConstraint(
            "recipe_equipment_id",
            "equipment_id",
            name=op.f("uq_equipment_options_recipe_equipment_id_equipment_id"),
        ),
    )
    op.create_index(
        "ix_equipment_options_equipment_id_recipe_id",
        "equipment_options",
        ["equipment_id", "recipe_id"],
    )
    for table in TIMESTAMPED:
        op.execute(
            f"CREATE TRIGGER {table}_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )
    op.add_column(
        "recipes",
        sa.Column(
            "equipment_checked", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )

    # The list to start from.
    ids: dict[str, uuid.UUID] = {}
    things, names, links = [], [], []
    listed = [(n, a, [], True) for n, a in ASSUMED] + [(n, a, c, False) for n, a, c in RECORDED]
    for name, _, _, assumed in listed:
        ids[name] = uuid.uuid4()
        things.append(
            {"id": ids[name], "name": name, "match_key": match_key(name), "assumed": assumed}
        )
    for name, others, broader, _ in listed:
        for other in others:
            names.append({"equipment_id": ids[name], "name": other, "match_key": match_key(other)})
        for counted in broader:
            links.append({"equipment_id": ids[name], "counts_as_id": ids[counted]})
    op.bulk_insert(equipment, things)
    op.bulk_insert(aliases, names)
    op.bulk_insert(counts_as, links)


def downgrade() -> None:
    op.drop_column("recipes", "equipment_checked")
    op.drop_table("equipment_options")
    op.drop_table("recipe_equipment")
    op.drop_table("equipment_counts_as")
    op.drop_table("equipment_aliases")
    op.drop_table("equipment")
