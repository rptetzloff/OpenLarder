<script setup lang="ts">
import { onMounted, ref } from "vue";
import { addByIsbn, type BookSummary } from "../books";
import type { Me } from "../me";

defineProps<{ user: Me | null | undefined }>();
document.title = "Books · OpenLarder";

const books = ref<BookSummary[] | null>(null);
const failed = ref(false);
const isbn = ref("");
const adding = ref(false);
const error = ref("");

onMounted(async () => {
  try {
    const res = await fetch("/api/books");
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
    location.href = `/books/${id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    adding.value = false;
  }
}
</script>

<template>
  <article>
    <h1>Books</h1>

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
    <ul v-else class="book-list">
      <li v-for="book in books" :key="book.id">
        <a :href="`/books/${book.id}`" class="book-card">
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
