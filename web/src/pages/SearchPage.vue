<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import {
  type IngredientSummary,
  listIngredients,
  type Named,
  type SearchResult,
  searchRecipes,
} from "../ingredients";

document.title = "Search · OpenLarder";

// The ingredients, and the book if the search is within one, are kept in
// the address (?book=…&i=…&i=…), so a search can be bookmarked or shared.
const MAX = 10;
const chosen = ref<Named[]>([]);
const book = ref<Named | null>(null);
const result = ref<SearchResult | null>(null);
const missing = ref(0);
const failed = ref(false);
const loading = ref(false);
let asked = 0;

async function run(more = false) {
  const mine = ++asked;
  const ids = chosen.value.map((i) => i.id);
  const url = new URL(location.href);
  url.searchParams.delete("i");
  for (const id of ids) url.searchParams.append("i", id);
  if (book.value) url.searchParams.set("book", book.value.id);
  else url.searchParams.delete("book");
  history.replaceState(null, "", url);
  failed.value = false;
  if (!ids.length) {
    result.value = null;
    return;
  }
  loading.value = true;
  try {
    const offset = more ? (result.value?.recipes.length ?? 0) : 0;
    const page = await searchRecipes(ids, offset, book.value?.id);
    if (mine !== asked) return;
    if (more && result.value) result.value.recipes.push(...page.recipes);
    else result.value = page;
  } catch {
    if (mine === asked) failed.value = true;
  } finally {
    if (mine === asked) loading.value = false;
  }
}

// Picking an ingredient.
const query = ref("");
const suggestions = ref<IngredientSummary[]>([]);
let typed = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
watch(query, () => {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const mine = ++typed;
    const q = query.value.trim();
    const found = q ? (await listIngredients(q).catch(() => null))?.ingredients : [];
    if (mine !== typed || !found) return;
    const taken = new Set(chosen.value.map((i) => i.id));
    suggestions.value = found.filter((i) => !taken.has(i.id)).slice(0, 8);
  }, 200);
});

function add(i: Named) {
  if (chosen.value.length >= MAX) return;
  chosen.value.push({ id: i.id, name: i.name });
  query.value = "";
  suggestions.value = [];
  document.getElementById("search-ingredient")?.focus();
  run();
}

function drop(id: string) {
  chosen.value = chosen.value.filter((i) => i.id !== id);
  run();
}

function everyBook() {
  book.value = null;
  run();
}

function where(r: SearchResult["recipes"][number]) {
  return r.pages.length ? `, p. ${r.pages.join(" / ")}` : "";
}

onMounted(async () => {
  const params = new URLSearchParams(location.search);
  const ids = params.getAll("i").slice(0, MAX);
  const bookId = params.get("book");
  try {
    if (!ids.length) {
      // Within a book, before any ingredient: the book's name is all to show.
      const res = bookId ? await fetch(`/api/books/${bookId}`) : null;
      if (res?.ok) {
        const found = await res.json();
        book.value = { id: found.id, name: found.title };
      }
      return;
    }
    // The search names the ingredients and book, so a link needs only IDs.
    const page = await searchRecipes(ids, 0, bookId);
    chosen.value = page.ingredients;
    book.value = page.book;
    missing.value = page.missing.length;
    result.value = page;
    if (page.missing.length) run();
  } catch {
    failed.value = true;
  }
});
</script>

<template>
  <article>
    <h1>Search</h1>
    <p class="status">
      Recipes that use every ingredient you choose, with the book and page to find them on.
    </p>

    <div class="isbn-form">
      <label for="search-ingredient">Add an ingredient</label>
      <div class="row">
        <input
          id="search-ingredient"
          v-model="query"
          type="search"
          autocomplete="off"
          placeholder="rhubarb"
          :disabled="chosen.length >= MAX"
          @keydown.enter.prevent="suggestions[0] && add(suggestions[0])"
        />
      </div>
      <ul v-if="suggestions.length" class="merge-candidates">
        <li v-for="s in suggestions" :key="s.id">
          <button type="button" class="link" @click="add(s)">{{ s.name }}</button>
          <span class="page-ref">
            {{ s.recipes.toLocaleString() }} {{ s.recipes === 1 ? "recipe" : "recipes" }}
          </span>
        </li>
      </ul>
      <p v-if="chosen.length >= MAX" class="status">That's as many as one search takes.</p>
    </div>

    <p v-if="book" class="search-book">
      In <a :href="`/books/${book.id}`">{{ book.name }}</a>
      <button type="button" class="link" @click="everyBook">Search every book</button>
    </p>
    <ul v-if="chosen.length" class="chosen" aria-label="Searching for">
      <li v-for="i in chosen" :key="i.id">
        <a :href="`/ingredients/${i.id}`">{{ i.name }}</a>
        <button type="button" class="link" :aria-label="`Remove ${i.name}`" @click="drop(i.id)">
          ×
        </button>
      </li>
    </ul>
    <p v-if="missing" class="status">
      {{ missing === 1 ? "One ingredient" : `${missing} ingredients` }} in this link no longer
      {{ missing === 1 ? "exists" : "exist" }}, perhaps merged into another, so the search is
      without {{ missing === 1 ? "it" : "them" }}.
    </p>

    <p v-if="failed" role="alert">The search didn't work. Try again.</p>
    <template v-else-if="result && chosen.length">
      <p class="status">
        {{ result.total.toLocaleString() }}
        {{ result.total === 1 ? "recipe uses" : "recipes use" }}
        {{ chosen.length > 1 ? "all of these" : "it" }}.
      </p>
      <ul class="recipe-list">
        <li v-for="r in result.recipes" :key="r.id">
          <a :href="`/recipes/${r.id}`">{{ r.title }}</a>
          <span class="page-ref">
            <a :href="`/books/${r.book_id}`">{{ r.book_title }}</a>{{ where(r) }}
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
