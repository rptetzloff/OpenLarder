<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import type { Book } from "../books";
import type { Me } from "../me";

const props = defineProps<{ id: string; user: Me | null | undefined }>();
const book = ref<Book | null>(null);
const missing = ref(false);
const failed = ref(false);

const byline = computed(() =>
  (book.value?.credits ?? [])
    .map((c) => (c.role === "author" ? c.credited_as : `${c.credited_as} (${c.role})`))
    .join(", "),
);
// "p. 112", or "p. 112 / 120" when editions differ; blank pages don't show.
function pages(list: (string | null)[]) {
  const known = [...new Set(list.filter((p): p is string => !!p))];
  return known.length ? `p. ${known.join(" / ")}` : "";
}
const cover = computed(() => book.value?.editions.find((e) => e.cover_url)?.cover_url ?? null);

onMounted(async () => {
  try {
    const res = await fetch(`/api/books/${props.id}`);
    if (res.status === 404 || res.status === 422) missing.value = true;
    else if (!res.ok) failed.value = true;
    else {
      book.value = await res.json();
      document.title = `${book.value!.title} · OpenLarder`;
    }
  } catch {
    failed.value = true;
  }
});
</script>

<template>
  <article>
    <p><a href="/books">← All books</a></p>
    <p v-if="missing">There's no book here. It may have been removed, or the link is wrong.</p>
    <p v-else-if="failed" role="alert">This book couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!book" class="status">Loading…</p>
    <template v-else>
      <div class="book-head">
        <img v-if="cover" :src="cover" :alt="`Cover of ${book.title}`" />
        <div>
          <h1>{{ book.title }}</h1>
          <p v-if="book.subtitle" class="subtitle">{{ book.subtitle }}</p>
          <p v-if="byline" class="byline">{{ byline }}</p>
        </div>
      </div>

      <h2>Recipes</h2>
      <p v-if="user?.is_admin"><a :href="`/books/${book.id}/recipes/new`">Add a recipe</a></p>
      <ul v-if="book.recipes.length" class="recipe-list">
        <li v-for="r in book.recipes" :key="r.id">
          <a :href="`/recipes/${r.id}`">{{ r.title }}</a>
          <span v-if="pages(r.pages)" class="page-ref">{{ pages(r.pages) }}</span>
        </li>
      </ul>
      <p v-else class="status">No recipes indexed yet.</p>

      <h2>Editions</h2>
      <ul class="editions">
        <li v-for="e in book.editions" :key="e.id">
          <strong>{{ e.title ?? book.title }}</strong>
          <span v-if="e.publisher || e.published_year">
            · {{ [e.publisher, e.published_year].filter(Boolean).join(", ") }}
          </span>
          <span v-if="e.isbn13"> · ISBN {{ e.isbn13 }}</span>
          <span v-if="e.open_library_url">
            · <a :href="e.open_library_url">Open Library</a>
          </span>
        </li>
      </ul>
      <!-- Open Library asks for a courtesy link back where its data is shown. -->
      <p class="status">
        Book details and covers from <a href="https://openlibrary.org">Open Library</a>.
      </p>
    </template>
  </article>
</template>
