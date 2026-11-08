<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { type BookSummary, findBooks } from "../books";
import {
  type IngredientSummary,
  listIngredients,
  type Named,
  type SearchResult,
  searchRecipes,
} from "../ingredients";

document.title = "Search · OpenLarder";

// What can I make from these books with what I have? Ingredients you have
// rank the recipes (the more of a recipe you have, the higher), title words and books
// narrow them. All of it is kept in the address (?book=…&q=…&i=…), so a
// search can be bookmarked or shared.
const MAX_INGREDIENTS = 30;
const MAX_BOOKS = 10;
const params = new URLSearchParams(location.search);
const chosen = ref<Named[]>([]);
const shelf = ref<Named[]>([]);
const title = ref(params.get("q") ?? "");
const result = ref<SearchResult | null>(null);
const missing = ref(0);
const failed = ref(false);
const loading = ref(false);
let asked = 0;

async function run(more = false) {
  const mine = ++asked;
  const ids = chosen.value.map((i) => i.id);
  const books = shelf.value.map((b) => b.id);
  const url = new URL(location.href);
  url.searchParams.delete("i");
  url.searchParams.delete("book");
  for (const id of books) url.searchParams.append("book", id);
  for (const id of ids) url.searchParams.append("i", id);
  if (title.value.trim()) url.searchParams.set("q", title.value.trim());
  else url.searchParams.delete("q");
  history.replaceState(null, "", url);
  failed.value = false;
  if (!ids.length && !title.value.trim()) {
    result.value = null;
    return;
  }
  loading.value = true;
  try {
    const offset = more ? (result.value?.recipes.length ?? 0) : 0;
    const page = await searchRecipes(ids, { offset, books, q: title.value });
    if (mine !== asked) return;
    if (more && result.value) result.value.recipes.push(...page.recipes);
    else result.value = page;
  } catch {
    if (mine === asked) failed.value = true;
  } finally {
    if (mine === asked) loading.value = false;
  }
}

let titleTimer: ReturnType<typeof setTimeout> | undefined;
watch(title, () => {
  clearTimeout(titleTimer);
  titleTimer = setTimeout(() => run(), 300);
});

// Type-to-find, for books and for ingredients: suggestions from the server,
// leaving out what's already chosen.
function finder<T extends Named>(
  find: (q: string) => Promise<T[]>,
  taken: () => Named[],
) {
  const query = ref("");
  const suggestions = ref<T[]>([]);
  let typed = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  watch(query, () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const mine = ++typed;
      const q = query.value.trim();
      const found = q ? await find(q).catch(() => null) : [];
      if (mine !== typed || !found) return;
      const ids = new Set(taken().map((t) => t.id));
      suggestions.value = found.filter((t) => !ids.has(t.id)).slice(0, 8);
    }, 200);
  });
  return { query, suggestions };
}

const ingredientFind = finder(
  async (q) => (await listIngredients(q)).ingredients,
  () => chosen.value,
);
const bookFind = finder(
  async (q) => (await findBooks(q)).map((b) => ({ ...b, name: b.title })),
  () => shelf.value,
);

function addTo(list: Named[], item: Named, max: number) {
  if (list.length < max) list.push({ id: item.id, name: item.name });
}

function addIngredient(item: Named) {
  addTo(chosen.value, item, MAX_INGREDIENTS);
  ingredientFind.query.value = "";
  ingredientFind.suggestions.value = [];
  document.getElementById("search-ingredient")?.focus();
  run();
}

function addBook(item: Named) {
  addTo(shelf.value, item, MAX_BOOKS);
  bookFind.query.value = "";
  bookFind.suggestions.value = [];
  document.getElementById("search-book")?.focus();
  run();
}

function dropIngredient(id: string) {
  chosen.value = chosen.value.filter((i) => i.id !== id);
  run();
}

function dropBook(id: string) {
  shelf.value = shelf.value.filter((b) => b.id !== id);
  run();
}

const summary = computed(() => {
  const r = result.value;
  if (!r) return "";
  const n = `${r.total.toLocaleString()} ${r.total === 1 ? "recipe" : "recipes"}`;
  const where = shelf.value.length ? ` in ${shelf.value.length === 1 ? "this book" : "these books"}` : "";
  const titled = r.q ? ` with “${r.q}” in the title` : "";
  if (!chosen.value.length) return `${n}${where}${titled}.`;
  return `${n}${where}${titled} use some of what you have, closest to made first.`;
});

function where(r: SearchResult["recipes"][number]) {
  return r.pages.length ? `, p. ${r.pages.join(" / ")}` : "";
}

onMounted(async () => {
  const ids = params.getAll("i").slice(0, MAX_INGREDIENTS);
  const books = params.getAll("book").slice(0, MAX_BOOKS);
  try {
    if (!ids.length && !title.value.trim()) {
      // Books, before anything to search by: their names are all to show.
      for (const id of books) {
        const res = await fetch(`/api/books/${id}`);
        if (res.ok) shelf.value.push({ id, name: (await res.json()).title });
      }
      if (shelf.value.length < books.length) run();
      return;
    }
    // The search names the ingredients and books, so a link needs only IDs.
    const page = await searchRecipes(ids, { books, q: title.value });
    chosen.value = page.ingredients;
    shelf.value = page.books;
    missing.value = page.missing.length + page.missing_books.length;
    result.value = page;
    if (missing.value) run();
  } catch {
    failed.value = true;
  }
});
</script>

<template>
  <article>
    <h1>Search</h1>
    <p class="status">
      Tell it what you have and which books are out, and it finds the recipes you're closest to
      making, with the book and page to find them on.
    </p>

    <div class="isbn-form">
      <label for="search-ingredient">Ingredients you have</label>
      <div class="row">
        <input
          id="search-ingredient"
          v-model="ingredientFind.query.value"
          type="search"
          autocomplete="off"
          placeholder="rhubarb"
          :disabled="chosen.length >= MAX_INGREDIENTS"
          @keydown.enter.prevent="
            ingredientFind.suggestions.value[0] &&
            addIngredient(ingredientFind.suggestions.value[0])
          "
        />
      </div>
      <ul v-if="ingredientFind.suggestions.value.length" class="merge-candidates">
        <li v-for="s in ingredientFind.suggestions.value" :key="s.id">
          <button
            type="button"
            class="link"
            @click="addIngredient(s)"
          >
            {{ s.name }}
          </button>
          <span class="page-ref">
            {{ s.recipes.toLocaleString() }} {{ s.recipes === 1 ? "recipe" : "recipes" }}
          </span>
        </li>
      </ul>
    </div>
    <ul v-if="chosen.length" class="chosen" aria-label="Ingredients you have">
      <li v-for="i in chosen" :key="i.id">
        <a :href="`/ingredients/${i.id}`">{{ i.name }}</a>
        <button
          type="button"
          class="link"
          :aria-label="`Remove ${i.name}`"
          @click="dropIngredient(i.id)"
        >
          ×
        </button>
      </li>
    </ul>

    <div class="isbn-form">
      <label for="search-book">Books</label>
      <div class="row">
        <input
          id="search-book"
          v-model="bookFind.query.value"
          type="search"
          autocomplete="off"
          placeholder="every book, or type a title or author"
          :disabled="shelf.length >= MAX_BOOKS"
          @keydown.enter.prevent="
            bookFind.suggestions.value[0] &&
            addBook(bookFind.suggestions.value[0])
          "
        />
      </div>
      <ul v-if="bookFind.suggestions.value.length" class="merge-candidates">
        <li v-for="b in bookFind.suggestions.value" :key="b.id">
          <button type="button" class="link" @click="addBook(b)">
            {{ b.title }}
          </button>
          <span v-if="b.authors.length" class="page-ref">{{ b.authors.join(", ") }}</span>
        </li>
      </ul>
    </div>
    <ul v-if="shelf.length" class="chosen" aria-label="Books">
      <li v-for="b in shelf" :key="b.id">
        <a :href="`/books/${b.id}`">{{ b.name }}</a>
        <button type="button" class="link" :aria-label="`Remove ${b.name}`" @click="dropBook(b.id)">
          ×
        </button>
      </li>
    </ul>

    <div class="isbn-form">
      <label for="search-title">Words in the title</label>
      <div class="row">
        <input
          id="search-title"
          v-model="title"
          type="search"
          autocomplete="off"
          maxlength="200"
          placeholder="cake"
        />
      </div>
    </div>

    <p v-if="missing" class="status">
      {{ missing === 1 ? "Something" : `${missing} things` }} in this link no longer
      {{ missing === 1 ? "exists" : "exist" }}, perhaps merged into another, so the search is
      without {{ missing === 1 ? "it" : "them" }}.
    </p>

    <p v-if="failed" role="alert">The search didn't work. Try again.</p>
    <template v-else-if="result && (chosen.length || result.q)">
      <p class="status">{{ summary }}</p>
      <ul class="recipe-list">
        <li v-for="r in result.recipes" :key="r.id">
          <a :href="`/recipes/${r.id}`">{{ r.title }}</a>
          <span class="page-ref">
            <a :href="`/books/${r.book_id}`">{{ r.book_title }}</a>{{ where(r) }}
          </span>
          <span v-if="r.lines !== null" class="match">
            <template v-if="!r.needs.length">You have everything it lists.</template>
            <template v-else>
              You have {{ r.have }} of {{ r.lines }}. Needs {{ r.needs.join(", ") }}.
            </template>
          </span>
        </li>
      </ul>
      <button
        v-if="result.recipes.length < result.total"
        type="button"
        class="primary"
        :disabled="loading"
        @click="run(true)"
      >
        Show more ({{ (result.total - result.recipes.length).toLocaleString() }} left)
      </button>
    </template>
  </article>
</template>
