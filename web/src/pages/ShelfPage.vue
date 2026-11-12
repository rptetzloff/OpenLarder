<script setup lang="ts">
import { computed, ref, watch } from "vue";
import CoverBlank from "../components/CoverBlank.vue";
import type { Me } from "../me";
import { myShelf, type ShelfBook, takeOffShelf } from "../shelf";

// Your shelf (routers/shelf.py): the books you own. SCOPING.md: "mark books
// you own, filter search to your shelf".
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Your shelf · OpenLarder";

const books = ref<ShelfBook[] | null>(null);
const error = ref("");
const busy = ref(false);
const filter = ref("");
const shown = computed(() => {
  const words = filter.value.toLowerCase().split(/\s+/).filter(Boolean);
  return (books.value ?? []).filter((b) => {
    const text = [b.title, b.subtitle, ...b.authors].join(" ").toLowerCase();
    return words.every((w) => text.includes(w));
  });
});
const recipes = computed(() => (books.value ?? []).reduce((n, b) => n + b.recipes, 0));

function editionLabel(b: ShelfBook) {
  return [b.edition_year, b.edition_isbn13 && `ISBN ${b.edition_isbn13}`]
    .filter(Boolean)
    .join(" · ");
}

async function load() {
  try {
    books.value = await myShelf();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function remove(b: ShelfBook) {
  busy.value = true;
  error.value = "";
  try {
    await takeOffShelf(b.id);
    books.value = (books.value ?? []).filter((x) => x.id !== b.id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

watch(
  () => props.user,
  (user) => {
    if (user && !books.value) load();
  },
  { immediate: true },
);
</script>

<template>
  <article class="wide shelf-page">
    <div class="list-head">
      <h1>Your shelf</h1>
      <p class="muted">
        The cookbooks you own. Search can keep to them, and a recipe's page opens at the page in
        the edition you have. Only you see your shelf. To add a book, open its page and choose “I
        have this book”.
      </p>
    </div>
    <p v-if="user === null" class="status">
      <a href="/api/auth/login">Sign in</a> to keep a shelf.
    </p>
    <template v-else-if="user">
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="!books && !error" class="status">Loading…</p>
      <template v-else-if="books">
        <p v-if="!books.length" class="status">
          Nothing on it yet. Find your books on <a href="/sources">Sources</a>.
        </p>
        <template v-else>
          <p class="status shelf-summary">
            {{ books.length.toLocaleString() }} {{ books.length === 1 ? "book" : "books" }},
            {{ recipes.toLocaleString() }} {{ recipes === 1 ? "recipe" : "recipes" }} indexed.
            <a href="/search?own=1" class="button-outline">Search my shelf</a>
          </p>
          <div v-if="books.length > 8" class="list-find">
            <label for="shelf-filter">Find on your shelf</label>
            <input
              id="shelf-filter"
              v-model="filter"
              type="search"
              autocomplete="off"
              placeholder="Title or author"
            />
          </div>
          <ul class="cover-grid">
            <li v-for="b in shown" :key="b.id">
              <a :href="`/sources/${b.id}`" class="cover-card">
                <img v-if="b.cover_url" :src="b.cover_url" alt="" loading="lazy" />
                <CoverBlank v-else :title="b.title" :byline="b.authors.join(', ')" :kind="b.kind" />
                <strong>{{ b.title }}</strong>
                <span v-if="b.authors.length" class="byline">{{ b.authors.join(", ") }}</span>
                <span v-if="b.editions > 1 && editionLabel(b)" class="byline"
                  >Yours: {{ editionLabel(b) }}</span
                >
                <span class="byline"
                  >{{ b.recipes.toLocaleString() }}
                  {{ b.recipes === 1 ? "recipe" : "recipes" }}</span
                >
              </a>
              <button
                type="button"
                class="link shelf-remove"
                :disabled="busy"
                :aria-label="`Take off ${b.title}`"
                @click="remove(b)"
              >
                Take off
              </button>
            </li>
          </ul>
          <p v-if="!shown.length" class="status">Nothing on your shelf matches “{{ filter }}”.</p>
        </template>
      </template>
    </template>
  </article>
</template>

<style scoped>
.shelf-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}
.shelf-remove {
  margin-top: 0.25rem;
}
</style>
