<script setup lang="ts">
import { ref } from "vue";
import { type BookSummary, listSources } from "../books";
import { archiveMissing } from "../recipes";
import type { Me } from "../me";

defineProps<{ user: Me | null | undefined }>();
document.title = "Admin · OpenLarder";

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
  <article>
    <h1>Admin</h1>
    <p v-if="!user?.is_admin" class="status">This is for admins.</p>
    <template v-else>
      <ul>
        <li><a href="/admin/import">Import</a>: add books and recipes from a book list and a recipe list.</li>
        <li><a href="/admin/imports">Import history</a>: every import, with its totals and report.</li>
        <li><a href="/admin/flags">Flagged recipes</a>: everything an entry or import flagged for a look.</li>
        <li><a href="/admin/suggestions">Suggestions</a>: ingredients a local model thinks are the same, or belong under another.</li>
      </ul>
      <h2>References and ingredients</h2>
      <p class="status">
        Links each “(p. 269)” in an ingredient list to the recipe on that page, and matches every
        other ingredient to its canonical ingredient, in every book. New and edited recipes are
        done as they're saved; this catches up the ones stored before.
      </p>
      <button type="button" class="primary" :disabled="linking" @click="linkAll">
        {{ linking ? "Linking…" : "Link references and ingredients" }}
      </button>
      <p v-if="progress" class="status" aria-live="polite">{{ progress }}</p>
      <p v-if="linkError" class="error" role="alert">{{ linkError }}</p>

      <h2>Internet Archive</h2>
      <p class="status">
        Each web recipe's page is copied to the Internet Archive when it's added, so a page that
        disappears can still be read. This asks again for the pages with no copy yet.
      </p>
      <button type="button" class="primary" @click="archiveAll">Archive pages without a copy</button>
      <p v-if="archiveNote" class="status" aria-live="polite">{{ archiveNote }}</p>
    </template>
  </article>
</template>
