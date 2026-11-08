<script setup lang="ts">
import { ref } from "vue";
import type { BookSummary } from "../books";
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
    const res = await fetch("/api/sources");
    if (!res.ok) throw new Error("The books couldn't be loaded.");
    const books: BookSummary[] = await res.json();
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
    </template>
  </article>
</template>
