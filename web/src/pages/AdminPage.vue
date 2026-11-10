<script setup lang="ts">
import { ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import { type WikidataRun, checkWikidata } from "../authors";
import { type BookSummary, listSources } from "../books";
import { fetchFlags } from "../flags";
import { reviewQueue } from "../review";
import { fetchSuggestions } from "../suggestions";
import { archiveMissing } from "../recipes";
import type { Me } from "../me";

const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Admin · OpenLarder";

// What's waiting, on each card; null until known, or if it couldn't be.
const openFlags = ref<number | null>(null);
const openSuggestions = ref<number | null>(null);
const waiting = ref<number | null>(null);
const imports = ref<number | null>(null);
const sum = (counts: Record<string, number>) => Object.values(counts).reduce((a, b) => a + b, 0);

async function loadCounts() {
  const [flags, suggestions, runs] = await Promise.allSettled([
    fetchFlags({ scope: "all", state: "open" }),
    fetchSuggestions({ state: "open" }),
    props.user?.may_run
      ? fetch("/api/import/runs").then((r) => (r.ok ? r.json() : Promise.reject()))
      : Promise.reject(),
    reviewQueue().then((q) => (waiting.value = q.pending)),
  ]);
  if (flags.status === "fulfilled") openFlags.value = sum(flags.value.open_by_kind);
  if (suggestions.status === "fulfilled") openSuggestions.value = sum(suggestions.value.open_by_kind);
  if (runs.status === "fulfilled") imports.value = runs.value.length;
}
// Who's signed in arrives after the page mounts.
watch(
  () => props.user?.may_edit,
  (yes) => {
    if (yes) loadCounts();
  },
  { immediate: true },
);
// Wikidata's facts for every author it may know (by Open Library or
// Wikidata ID), a batch at a time; each batch is one query.
const asking = ref(false);
const asked = ref("");
const askError = ref("");
const clashes = ref<WikidataRun["clashes"]>([]);
async function askWikidata() {
  asking.value = true;
  askError.value = "";
  clashes.value = [];
  let checked = 0;
  let found = 0;
  try {
    for (;;) {
      const run = await checkWikidata();
      checked += run.checked;
      found += run.found;
      clashes.value.push(...run.clashes);
      asked.value = `${checked.toLocaleString()} asked about, ${found.toLocaleString()} found; ${run.remaining.toLocaleString()} to go.`;
      if (!run.remaining || !run.checked) break;
    }
    asked.value = checked
      ? `Done: ${n(checked, "author", "authors")} asked about, ${found.toLocaleString()} found on Wikidata.`
      : "Every author has been asked about lately.";
  } catch (e) {
    askError.value = e instanceof Error ? e.message : String(e);
  } finally {
    asking.value = false;
  }
}

const n = (v: number | null, one: string, many: string) =>
  v === null ? "" : `${v.toLocaleString()} ${v === 1 ? one : many}`;

// Links page references and matches ingredients in recipes stored before
// either existed. One
// request a book, so none runs long; running it again changes nothing.
const linking = ref(false);
const progress = ref("");
const linkError = ref("");

async function linkAll() {
  linking.value = true;
  linkError.value = "";
  try {
    // Every source, a page at a time.
    const books: BookSummary[] = [];
    for (let total = 1; books.length < total; ) {
      const page = await listSources("", books.length);
      books.push(...page.sources);
      total = page.total;
      if (!page.sources.length) break;
    }
    let linked = 0;
    for (const [i, book] of books.entries()) {
      progress.value = `${i + 1} of ${books.length}: ${book.title}`;
      const done = await fetch(`/api/sources/${book.id}/references`, { method: "POST" });
      if (!done.ok) throw new Error(`${book.title} couldn't be linked. Try again.`);
      linked += (await done.json()).linked;
    }
    progress.value = `Done: ${books.length.toLocaleString()} books, ${linked.toLocaleString()} references linked.`;
  } catch (e) {
    linkError.value = e instanceof Error ? e.message : String(e);
  } finally {
    linking.value = false;
  }
}

// Web recipes' pages with no Internet Archive copy yet, as when the Archive
// was down when they were added.
const archiveNote = ref("");
async function archiveAll() {
  try {
    const pages = await archiveMissing();
    archiveNote.value = pages
      ? `Asked the Internet Archive for ${pages} ${pages === 1 ? "page" : "pages"}, one at a time.`
      : "Every web page has a copy already.";
  } catch (e) {
    archiveNote.value = e instanceof Error ? e.message : String(e);
  }
}
</script>

<template>
  <AdminBar v-if="user?.may_edit" :user="user" current="/admin" />
  <article class="wide admin-page">
    <div class="list-head">
      <h1>Admin</h1>
      <p class="muted">Keeping the catalog in order: what's been flagged or suggested, and imports.</p>
    </div>
    <p v-if="!user?.may_edit" class="status">This is for moderators.</p>
    <template v-else>
      <ul class="link-cards">
        <li>
          <a href="/admin/review">
            <h2>Review</h2>
            <p class="count">{{ n(waiting, "waiting", "waiting") }}</p>
            <p>Books and recipes contributors have added, for a moderator to approve.</p>
          </a>
        </li>
        <li>
          <a href="/admin/flags">
            <h2>Flagged recipes</h2>
            <p class="count">{{ n(openFlags, "open", "open") }}</p>
            <p>Anything an entry or import flagged for a look.</p>
          </a>
        </li>
        <li>
          <a href="/admin/suggestions">
            <h2>Suggestions</h2>
            <p class="count">{{ n(openSuggestions, "open", "open") }}</p>
            <p>Ingredients a local model thinks are the same, or belong under another.</p>
          </a>
        </li>
        <li v-if="user.may_run">
          <a href="/admin/import">
            <h2>Bulk import</h2>
            <p>Add books and recipes from a book list and a recipe list.</p>
          </a>
        </li>
        <li v-if="user.may_run">
          <a href="/admin/api">
            <h2>API usage</h2>
            <p>Programs reading the API, busiest first, to spot abuse; keys can be revoked there.</p>
          </a>
        </li>
        <li v-if="user.may_run">
          <a href="/admin/clicks">
            <h2>Buy-link clicks</h2>
            <p>Clicks on the shops' links, by shop, book, page and day.</p>
          </a>
        </li>
        <li>
          <a href="/admin/changes">
            <h2>Recent changes</h2>
            <p>Everything added, changed or removed in the catalog, by whom.</p>
          </a>
        </li>
        <li>
          <a href="/admin/people">
            <h2>People and roles</h2>
            <p>Contributors, moderators and administrators, and who can make whom one.</p>
          </a>
        </li>
        <li v-if="user.may_run">
          <a href="/admin/imports">
            <h2>Import history</h2>
            <p class="count">{{ n(imports, "import", "imports") }}</p>
            <p>Every import, with its totals and report.</p>
          </a>
        </li>
      </ul>

      <h2 class="section-title">Catching up</h2>
      <div class="tool-panels">
        <section class="tool-panel" aria-labelledby="link-title">
          <h3 id="link-title">References and ingredients</h3>
          <p class="muted">
            Links each “(p. 269)” in an ingredient list to the recipe on that page, and matches
            every other ingredient to its canonical ingredient, in every book. New and edited
            recipes are done as they're saved; this catches up the ones stored before.
          </p>
          <button type="button" class="primary" :disabled="linking" @click="linkAll">
            {{ linking ? "Linking…" : "Link references and ingredients" }}
          </button>
          <p v-if="progress" class="status" aria-live="polite">{{ progress }}</p>
          <p v-if="linkError" class="error" role="alert">{{ linkError }}</p>
        </section>
        <section class="tool-panel" aria-labelledby="archive-title">
          <h3 id="archive-title">Internet Archive</h3>
          <p class="muted">
            Each web recipe's page is copied to the Internet Archive when it's added, so a page that
            disappears can still be read. This asks again for the pages with no copy yet.
          </p>
          <button type="button" class="primary" @click="archiveAll">Archive pages without a copy</button>
          <p v-if="archiveNote" class="status" aria-live="polite">{{ archiveNote }}</p>
        </section>
        <section class="tool-panel" aria-labelledby="wikidata-title">
          <h3 id="wikidata-title">Wikidata facts</h3>
          <p class="muted">
            Born and died, country and website for each author Wikidata knows, found by their Open
            Library record. Each is asked about again after a month, since Wikidata grows.
          </p>
          <button type="button" class="primary" :disabled="asking" @click="askWikidata">
            {{ asking ? "Asking…" : "Fetch Wikidata facts" }}
          </button>
          <p v-if="asked" class="status" aria-live="polite">{{ asked }}</p>
          <p v-if="askError" class="error" role="alert">{{ askError }}</p>
          <template v-if="clashes.length">
            <p class="status">
              These fit an item another author has already; probably one person twice. Merge them
              from the author's page:
            </p>
            <ul class="clash-list">
              <li v-for="c in clashes" :key="c.author.id">
                <a :href="`/authors/${c.author.id}`">{{ c.author.name }}</a> and
                <a :href="`/authors/${c.other.id}`">{{ c.other.name }}</a>
              </li>
            </ul>
          </template>
        </section>
      </div>
    </template>
  </article>
</template>
