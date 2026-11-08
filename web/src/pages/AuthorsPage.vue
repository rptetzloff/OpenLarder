<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { type AuthorSummary, listAuthors } from "../authors";

document.title = "Authors · OpenLarder";

const q = ref(new URLSearchParams(location.search).get("q") ?? "");
const authors = ref<AuthorSummary[] | null>(null);
const total = ref(0);
const failed = ref(false);
const loading = ref(false);
// Answers can arrive out of order as someone types; only the latest counts.
let asked = 0;

async function load(more = false) {
  const mine = ++asked;
  loading.value = true;
  failed.value = false;
  try {
    const page = await listAuthors(q.value, more ? (authors.value?.length ?? 0) : 0);
    if (mine !== asked) return;
    authors.value = more ? [...(authors.value ?? []), ...page.authors] : page.authors;
    total.value = page.total;
  } catch {
    if (mine === asked) failed.value = true;
  } finally {
    if (mine === asked) loading.value = false;
  }
}

let timer: ReturnType<typeof setTimeout> | undefined;
watch(q, () => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    const url = new URL(location.href);
    if (q.value.trim()) url.searchParams.set("q", q.value.trim());
    else url.searchParams.delete("q");
    history.replaceState(null, "", url);
    load();
  }, 200);
});
onMounted(() => load());
</script>

<template>
  <article>
    <p><a href="/sources">← Books</a></p>
    <h1>Authors</h1>
    <div class="isbn-form">
      <label for="author-filter">Find an author</label>
      <div class="row">
        <input
          id="author-filter"
          v-model="q"
          type="search"
          autocomplete="off"
          placeholder="ottolenghi"
        />
      </div>
    </div>
    <p v-if="failed" role="alert">The authors couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="authors === null" class="status">Loading…</p>
    <p v-else-if="authors.length === 0" class="status">
      {{ q.trim() ? `No author matches “${q.trim()}”.` : "No authors yet." }}
    </p>
    <template v-else>
      <p class="status">
        {{ total.toLocaleString() }} {{ total === 1 ? "author" : "authors" }}
      </p>
      <ul class="recipe-list">
        <li v-for="a in authors" :key="a.id">
          <a :href="`/authors/${a.id}`">{{ a.name }}</a>
          <span class="page-ref">{{ a.sources }} {{ a.sources === 1 ? "book" : "books" }}</span>
        </li>
      </ul>
      <button
        v-if="authors.length < total"
        type="button"
        class="primary"
        :disabled="loading"
        @click="load(true)"
      >
        Show more ({{ (total - authors.length).toLocaleString() }} left)
      </button>
    </template>
  </article>
</template>
