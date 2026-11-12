<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { type Book, type BookSummary, findBooks } from "../books";
import { searchRecipes, type SearchResult } from "../ingredients";
import {
  addDiet,
  addSwap,
  type Diet,
  listDiets,
  side,
  type Swap,
  type Thing,
} from "../substitutions";
import IngredientPicker from "./IngredientPicker.vue";

// Adding a swap. `choices` are what it can replace: one, fixed, on an
// ingredient's page; a recipe's ingredients, cited recipes and itself on a
// recipe's page, where the source starts as the recipe's book and page.
const props = defineProps<{
  choices: Thing[];
  bookId?: string | null;
  editionId?: string | null;
  page?: string | null;
}>();
const emit = defineEmits<{ added: [swap: Swap] }>();

const insteadOf = ref<string>(props.choices[0]?.id ?? "");
const useKind = ref<"ingredient" | "recipe">("ingredient");
const use = ref<Thing | null>(null);

const diets = ref<Diet[]>([]);
// A diet's ID, "" for none, or "new" to type one.
const dietId = ref("");
const newDiet = ref("");

// The book it's printed in, found by typing: the catalog is too big for a
// list to choose from.
const bookTitle = ref("");
const bookQuery = ref("");
const bookHits = ref<BookSummary[]>([]);
const printed = ref(!!props.bookId);
const bookId = ref(props.bookId ?? "");
const editions = ref<Book["editions"]>([]);
const editionId = ref(props.editionId ?? "");
const page = ref(props.page ?? "");
const note = ref("");

const error = ref("");
const saving = ref(false);

onMounted(async () => {
  try {
    diets.value = await listDiets();
  } catch {
    error.value = "The form couldn't load its lists. Try reloading the page.";
  }
});

watch(
  bookId,
  async (id, before) => {
    editions.value = [];
    if (!id) {
      editionId.value = "";
      bookTitle.value = "";
      return;
    }
    const res = await fetch(`/api/sources/${id}`);
    if (!res.ok) return;
    const found = await res.json();
    editions.value = found.editions;
    bookTitle.value = found.title;
    // A different book: its first edition, and the page starts over.
    if (before !== undefined || !editionId.value) editionId.value = editions.value[0]?.id ?? "";
    if (before !== undefined) page.value = "";
  },
  { immediate: true },
);

let bookAsked = 0;
let bookTimer: ReturnType<typeof setTimeout> | undefined;
watch(bookQuery, () => {
  clearTimeout(bookTimer);
  bookTimer = setTimeout(async () => {
    const mine = ++bookAsked;
    const q = bookQuery.value.trim();
    // Only a book has editions and pages to print a swap on.
    const found = q ? (await findBooks(q).catch(() => [])).filter((b) => b.kind === "book") : [];
    if (mine === bookAsked) bookHits.value = found;
  }, 200);
});

function pickBook(b: BookSummary) {
  bookId.value = b.id;
  bookQuery.value = "";
  bookHits.value = [];
}

// Finding a recipe to stand in, by title.
const recipeQuery = ref("");
const recipeHits = ref<SearchResult["recipes"]>([]);
let asked = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
watch(recipeQuery, () => {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const mine = ++asked;
    const q = recipeQuery.value.trim();
    const found = q ? await searchRecipes([], { q }).catch(() => null) : null;
    if (mine === asked) recipeHits.value = found?.recipes.slice(0, 8) ?? [];
  }, 250);
});

function pickRecipe(r: SearchResult["recipes"][number]) {
  use.value = { kind: "recipe", id: r.id, name: r.title };
  recipeQuery.value = "";
  recipeHits.value = [];
}

async function save() {
  const replaced = props.choices.find((c) => c.id === insteadOf.value);
  if (!replaced || !use.value) {
    error.value = "Choose what it replaces and what stands in.";
    return;
  }
  error.value = "";
  saving.value = true;
  try {
    let diet: string | null = dietId.value || null;
    if (diet === "new") {
      const made = await addDiet(newDiet.value);
      diets.value = [...diets.value.filter((d) => d.id !== made.id), made].sort((a, b) =>
        a.name.localeCompare(b.name),
      );
      dietId.value = diet = made.id;
    }
    const swap = await addSwap({
      instead_of: side(replaced),
      use: side(use.value),
      diet_id: diet,
      source_edition_id: printed.value ? editionId.value || null : null,
      source_page: printed.value ? page.value.trim() || null : null,
      note: note.value.trim() || null,
    });
    emit("added", swap);
    use.value = null;
    note.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <form class="recipe-form swap-form" @submit.prevent="save">
    <label for="swap-instead-of">Instead of</label>
    <select v-if="choices.length > 1" id="swap-instead-of" v-model="insteadOf">
      <option v-for="c in choices" :key="c.id" :value="c.id">
        {{ c.name }}{{ c.kind === "recipe" ? " (recipe)" : "" }}
      </option>
    </select>
    <p v-else id="swap-instead-of">{{ choices[0]?.name }}</p>

    <fieldset>
      <legend>Use</legend>
      <label class="check"
        ><input v-model="useKind" type="radio" value="ingredient" /> an ingredient</label
      >
      <label class="check"
        ><input v-model="useKind" type="radio" value="recipe" /> a recipe</label
      >
      <p v-if="use">
        <strong>{{ use.name }}</strong>
        <button type="button" class="secondary small" @click="use = null">Change</button>
      </p>
      <IngredientPicker
        v-else-if="useKind === 'ingredient'"
        input-id="swap-use"
        label="Ingredient"
        placeholder="coconut oil"
        :exclude="[insteadOf]"
        @pick="(i) => (use = { kind: 'ingredient', id: i.id, name: i.name })"
      />
      <div v-else class="isbn-form">
        <label for="swap-use-recipe">Recipe, by title</label>
        <div class="row">
          <input
            id="swap-use-recipe"
            v-model="recipeQuery"
            type="search"
            autocomplete="off"
            placeholder="flax egg"
          />
        </div>
        <ul v-if="recipeHits.length" class="merge-candidates">
          <li v-for="r in recipeHits" :key="r.id">
            <button type="button" class="link" @click="pickRecipe(r)">{{ r.title }}</button>
            <span class="page-ref">{{ r.source_title }}</span>
          </li>
        </ul>
      </div>
    </fieldset>

    <label for="swap-diet">For a diet</label>
    <select id="swap-diet" v-model="dietId">
      <option value="">None in particular</option>
      <option v-for="d in diets" :key="d.id" :value="d.id">{{ d.name }}</option>
      <option value="new">Another diet…</option>
    </select>
    <input
      v-if="dietId === 'new'"
      v-model="newDiet"
      aria-label="The diet's name"
      placeholder="Nightshade-Free"
      maxlength="60"
      required
    />

    <fieldset>
      <legend>Where it's from</legend>
      <label class="check"><input v-model="printed" type="radio" :value="true" /> printed in a book</label>
      <label class="check"
        ><input v-model="printed" type="radio" :value="false" /> contributed (not printed)</label
      >
      <template v-if="printed">
        <template v-if="bookId">
          <span>Book</span>
          <p>
            <strong>{{ bookTitle || "…" }}</strong>
            <button type="button" class="secondary small" @click="bookId = ''">Change</button>
          </p>
        </template>
        <div v-else class="isbn-form">
          <label for="swap-book">Book</label>
          <div class="row">
            <input
              id="swap-book"
              v-model="bookQuery"
              type="search"
              autocomplete="off"
              placeholder="title or author"
            />
          </div>
          <ul v-if="bookHits.length" class="merge-candidates">
            <li v-for="b in bookHits" :key="b.id">
              <button type="button" class="link" @click="pickBook(b)">{{ b.title }}</button>
              <span v-if="b.authors.length" class="page-ref">{{ b.authors.join(", ") }}</span>
            </li>
          </ul>
        </div>
        <template v-if="editions.length > 1">
          <label for="swap-edition">Edition</label>
          <select id="swap-edition" v-model="editionId">
            <option v-for="e in editions" :key="e.id" :value="e.id">
              {{ [e.title, e.publisher, e.published_year, e.isbn13 && `ISBN ${e.isbn13}`]
                .filter(Boolean)
                .join(" · ") || "Edition" }}
            </option>
          </select>
        </template>
        <label for="swap-page">Page</label>
        <input id="swap-page" v-model="page" class="page-input" maxlength="20" placeholder="12" />
      </template>
    </fieldset>

    <label for="swap-note">Note</label>
    <input
      id="swap-note"
      v-model="note"
      maxlength="300"
      placeholder="3 tablespoons aquafaba per egg"
    />

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <button type="submit" class="primary" :disabled="saving || !use">
      {{ saving ? "Adding…" : "Add the swap" }}
    </button>
  </form>
</template>
