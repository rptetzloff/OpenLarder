<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { addByIsbn, addWebsite, type BookSummary, listSources } from "../books";
import type { Me } from "../me";

defineProps<{ user: Me | null | undefined }>();
document.title = "Sources · OpenLarder";

const books = ref<BookSummary[] | null>(null);
const total = ref(0);
const failed = ref(false);
const loading = ref(false);
const isbn = ref("");
const adding = ref(false);
const error = ref("");

// A page of sources at a time, narrowed on the server as someone types (by
// title, subtitle, author or a website's address): the whole catalog is too
// much for one answer.
const filter = ref(new URLSearchParams(location.search).get("q") ?? "");
// Answers can arrive out of order as someone types; only the latest counts.
let asked = 0;

async function load(more = false) {
  const mine = ++asked;
  loading.value = true;
  failed.value = false;
  try {
    const page = await listSources(filter.value, more ? (books.value?.length ?? 0) : 0);
    if (mine !== asked) return;
    books.value = more ? [...(books.value ?? []), ...page.sources] : page.sources;
    total.value = page.total;
  } catch {
    if (mine === asked) failed.value = true;
  } finally {
    if (mine === asked) loading.value = false;
  }
}

let timer: ReturnType<typeof setTimeout> | undefined;
watch(filter, () => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    const url = new URL(location.href);
    if (filter.value.trim()) url.searchParams.set("q", filter.value.trim());
    else url.searchParams.delete("q");
    history.replaceState(null, "", url);
    load();
  }, 200);
});
onMounted(() => load());

// Adding a website: any address on it finds the site.
const siteAddress = ref("");
const siteName = ref("");
const sitePaywalled = ref(false);
// Who writes it: names separated by commas.
const siteAuthors = ref("");
const siteError = ref("");
async function addSite() {
  siteError.value = "";
  try {
    const authors = siteAuthors.value.split(",").map((a) => a.trim()).filter(Boolean);
    const { id } = await addWebsite(siteAddress.value, siteName.value, sitePaywalled.value, authors);
    location.href = `/sources/${id}`;
  } catch (e) {
    siteError.value = e instanceof Error ? e.message : String(e);
  }
}

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
    <h1>Sources</h1>
    <p class="status">Cookbooks and recipe websites, with the recipes indexed from them.</p>
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

    <form v-if="user?.is_admin" class="recipe-form site-form" @submit.prevent="addSite">
      <label for="site-address">Add a website: any page on it</label>
      <input
        id="site-address"
        v-model="siteAddress"
        required
        autocomplete="off"
        placeholder="https://smittenkitchen.com"
      />
      <label for="site-name">What it calls itself (optional)</label>
      <input id="site-name" v-model="siteName" maxlength="300" placeholder="Smitten Kitchen" />
      <label for="site-authors">Who writes it (optional; separate names with commas)</label>
      <input id="site-authors" v-model="siteAuthors" maxlength="500" placeholder="Deb Perelman" />
      <label class="check"
        ><input v-model="sitePaywalled" type="checkbox" /> Behind a subscription</label
      >
      <p v-if="siteError" class="error" role="alert">{{ siteError }}</p>
      <button type="submit" class="primary">Add the website</button>
    </form>

    <div class="isbn-form">
      <label for="book-filter">Find a source</label>
      <div class="row">
        <input
          id="book-filter"
          v-model="filter"
          type="search"
          autocomplete="off"
          placeholder="title, author or website"
        />
      </div>
    </div>
    <p v-if="failed" role="alert">The sources couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="books === null" class="status">Loading…</p>
    <p v-else-if="total === 0 && !filter.trim()">No sources yet.</p>
    <p v-else class="status">
      {{ total.toLocaleString() }} {{ total === 1 ? "source" : "sources" }}<template
        v-if="filter.trim()"
      >
        {{ total === 1 ? "matches" : "match" }} “{{ filter.trim() }}”</template
      >.
      <a v-if="total === 0" :href="`/search?q=${encodeURIComponent(filter.trim())}`"
        >Look for recipes with “{{ filter.trim() }}” in the title instead</a
      >
    </p>
    <ul v-if="books?.length" class="book-list">
      <li v-for="book in books" :key="book.id">
        <a :href="`/sources/${book.id}`" class="book-card">
          <img v-if="book.cover_url" :src="book.cover_url" alt="" loading="lazy" />
          <span v-else class="no-cover" aria-hidden="true"></span>
          <span>
            <strong>{{ book.title }}</strong>
            <span v-if="book.authors.length" class="byline">{{ book.authors.join(", ") }}</span>
            <span v-else-if="book.host" class="byline">{{ book.host }}</span>
          </span>
        </a>
      </li>
    </ul>
    <button
      v-if="books && books.length < total"
      type="button"
      class="primary"
      :disabled="loading"
      @click="load(true)"
    >
      Show more ({{ (total - books.length).toLocaleString() }} left)
    </button>
  </article>
</template>
