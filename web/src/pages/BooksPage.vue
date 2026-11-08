<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { addByIsbn, type BookSummary } from "../books";
import type { Me } from "../me";

defineProps<{ user: Me | null | undefined }>();
document.title = "Books · OpenLarder";

const books = ref<BookSummary[] | null>(null);
const failed = ref(false);
const isbn = ref("");
const adding = ref(false);
const error = ref("");

// Narrowing the list as someone types: by title, subtitle or author,
// ignoring case and accents. The whole list is here already.
const filter = ref(new URLSearchParams(location.search).get("q") ?? "");
const fold = (s: string) =>
  s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLocaleLowerCase();
const shown = computed(() => {
  const words = fold(filter.value).split(/\s+/).filter(Boolean);
  if (!books.value || !words.length) return books.value;
  return books.value.filter((b) => {
    const text = fold([b.title, b.subtitle ?? "", ...b.authors].join(" "));
    return words.every((w) => text.includes(w));
  });
});
watch(filter, () => {
  const url = new URL(location.href);
  if (filter.value.trim()) url.searchParams.set("q", filter.value.trim());
  else url.searchParams.delete("q");
  history.replaceState(null, "", url);
});

onMounted(async () => {
  try {
    const res = await fetch("/api/sources");
    books.value = res.ok ? await res.json() : null;
    failed.value = !res.ok;
  } catch {
    failed.value = true;
  }
});

async function add() {
  adding.value = true;
  error.value = "";
  try {
    const { id } = await addByIsbn(isbn.value);
    // A full load, so the new book's page fetches what was just stored.
    location.href = `/sources/${id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    adding.value = false;
  }
}
</script>

<template>
  <article>
    <h1>Books</h1>
    <p class="status"><a href="/authors">Browse by author</a></p>

    <form v-if="user?.is_admin" class="isbn-form" @submit.prevent="add">
      <label for="isbn">Add a book by ISBN</label>
      <div class="row">
        <input
          id="isbn"
          v-model="isbn"
          inputmode="numeric"
          autocomplete="off"
          placeholder="978-0-393-54111-3"
          required
          :aria-invalid="error ? 'true' : undefined"
          aria-describedby="isbn-error"
        />
        <button type="submit" class="primary" :disabled="adding">
          {{ adding ? "Looking it up…" : "Add" }}
        </button>
      </div>
      <p v-if="error" id="isbn-error" class="error" role="alert">{{ error }}</p>
    </form>

    <p v-if="failed" role="alert">The books couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="books === null" class="status">Loading…</p>
    <p v-else-if="books.length === 0">No books yet.</p>
    <template v-else>
      <div class="isbn-form">
        <label for="book-filter">Find a book</label>
        <div class="row">
          <input
            id="book-filter"
            v-model="filter"
            type="search"
            autocomplete="off"
            placeholder="title or author"
          />
        </div>
      </div>
      <p v-if="filter.trim()" class="status">
        {{ shown!.length }} of {{ books.length }} books.
        <a v-if="shown!.length === 0" :href="`/search?q=${encodeURIComponent(filter.trim())}`"
          >Look for recipes with “{{ filter.trim() }}” in the title instead</a
        >
      </p>
    </template>
    <ul v-if="shown?.length" class="book-list">
      <li v-for="book in shown" :key="book.id">
        <a :href="`/sources/${book.id}`" class="book-card">
          <img v-if="book.cover_url" :src="book.cover_url" alt="" loading="lazy" />
          <span v-else class="no-cover" aria-hidden="true"></span>
          <span>
            <strong>{{ book.title }}</strong>
            <span v-if="book.authors.length" class="byline">{{ book.authors.join(", ") }}</span>
          </span>
        </a>
      </li>
    </ul>
  </article>
</template>
