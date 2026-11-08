<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { type Book, issueName, KIND_NAMES } from "../books";
import OpenLibraryCheck from "../components/OpenLibraryCheck.vue";
import OpenLibraryLink from "../components/OpenLibraryLink.vue";
import type { Me } from "../me";

const props = defineProps<{ id: string; user: Me | null | undefined }>();
const book = ref<Book | null>(null);
const missing = ref(false);
const failed = ref(false);

// Each name links to its author; a role other than author is said.
const credits = computed(() =>
  (book.value?.credits ?? []).map((c) => ({
    ...c,
    role: c.role === "author" ? "" : ` (${c.role})`,
  })),
);
// "p. 112", or "p. 112 / 120" when editions differ; blank pages don't show.
function pages(list: (string | null)[]) {
  const known = [...new Set(list.filter((p): p is string => !!p))];
  return known.length ? `p. ${known.join(" / ")}` : "";
}
const cover = computed(() => book.value?.editions.find((e) => e.cover_url)?.cover_url ?? null);

async function load() {
  try {
    const res = await fetch(`/api/sources/${props.id}`);
    if (res.status === 404 || res.status === 422) missing.value = true;
    else if (!res.ok) failed.value = true;
    else {
      book.value = await res.json();
      document.title = `${book.value!.title} · OpenLarder`;
    }
  } catch {
    failed.value = true;
  }
}

onMounted(load);
</script>

<template>
  <article>
    <p><a href="/sources">← All sources</a></p>
    <p v-if="missing">There's no book here. It may have been removed, or the link is wrong.</p>
    <p v-else-if="failed" role="alert">This book couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!book" class="status">Loading…</p>
    <template v-else>
      <div class="book-head">
        <img v-if="cover" :src="cover" :alt="`Cover of ${book.title}`" />
        <div>
          <h1>{{ book.title }}</h1>
          <p v-if="book.subtitle" class="subtitle">{{ book.subtitle }}</p>
          <p v-if="book.host" class="byline">
            <a :href="`https://${book.host}`" rel="nofollow noopener">{{ book.host }}</a>
            <template v-if="book.paywalled"> · subscription site</template>
          </p>
          <p v-if="credits.length" class="byline">
            <template v-for="(c, i) in credits" :key="i"
              ><template v-if="i > 0">, </template
              ><a :href="`/authors/${c.author_id}`">{{ c.credited_as }}</a>{{ c.role }}</template
            >
          </p>
          <p v-if="book.open_library_url" class="byline">
            <a :href="book.open_library_url">On Open Library</a>
          </p>
          <p v-if="user?.is_admin" class="byline">
            <a :href="`/sources/${book.id}/edit`">Edit {{ KIND_NAMES[book.kind] }}</a>
          </p>
        </div>
      </div>

      <template v-if="book.ingredients.length">
        <h2>Ingredients</h2>
        <p class="status">
          The ones its recipes use most. Open one for the recipes here that use it, or
          <a :href="`/search?source=${book.id}`"
            >search this {{ KIND_NAMES[book.kind] }} by ingredient</a
          >.
        </p>
        <ul class="chosen">
          <li v-for="i in book.ingredients" :key="i.id">
            <a :href="`/search?source=${book.id}&i=${i.id}`">{{ i.name }}</a>
            <span class="page-ref">{{ i.recipes }}</span>
          </li>
        </ul>
      </template>

      <h2>Recipes</h2>
      <p v-if="user?.is_admin"><a :href="`/sources/${book.id}/recipes/new`">Add a recipe</a></p>
      <ul v-if="book.recipes.length" class="recipe-list">
        <li v-for="r in book.recipes" :key="r.id">
          <a :href="`/recipes/${r.id}`">{{ r.title }}</a>
          <span v-if="r.issue" class="page-ref"
            >{{ issueName(r.issue) }}{{ r.pages[0] ? `, p. ${r.pages[0]}` : "" }}</span
          >
          <span v-else-if="pages(r.pages)" class="page-ref">{{ pages(r.pages) }}</span>
        </li>
      </ul>
      <p v-else class="status">No recipes indexed yet.</p>

      <template v-if="book.kind === 'book'">
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
      <OpenLibraryLink v-if="user?.is_admin && !book.open_library_url" :book="book" />
      <OpenLibraryCheck v-if="user?.is_admin && book.open_library_url" :book-id="book.id" @taken="load" />

      <!-- Open Library asks for a courtesy link back where its data is shown. -->
      <p class="status">
        Book details and covers from <a href="https://openlibrary.org">Open Library</a>.
      </p>
      </template>
    </template>
  </article>
</template>
