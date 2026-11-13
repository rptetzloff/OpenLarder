<script setup lang="ts">
import { ref, watch } from "vue";
import OptionList from "./OptionList.vue";
import { type BookSummary, findBooks, mergeBook, mergePlan, type MergePlan } from "../books";

// Merging this book into another record of the same book (book_merge.py):
// find the other, see what would move, then merge. For moderators.
const props = defineProps<{ id: string; title: string }>();

const query = ref("");
const candidates = ref<BookSummary[]>([]);
const chosen = ref<BookSummary | null>(null);
const plan = ref<MergePlan | null>(null);
const error = ref("");
const busy = ref(false);
let asked = 0;

watch(query, async () => {
  const q = query.value.trim();
  const mine = ++asked;
  if (q.length < 2) {
    candidates.value = [];
    return;
  }
  const found = await findBooks(q).catch(() => []);
  if (mine === asked) candidates.value = found.filter((b) => b.id !== props.id && b.kind === "book");
});

async function choose(book: BookSummary) {
  chosen.value = book;
  plan.value = null;
  error.value = "";
  try {
    plan.value = await mergePlan(props.id, book.id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function merge() {
  if (!chosen.value) return;
  busy.value = true;
  error.value = "";
  try {
    const kept = await mergeBook(props.id, chosen.value.id);
    location.href = `/sources/${kept}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    busy.value = false;
  }
}
</script>

<template>
  <section id="merge" class="source-section book-merge" aria-labelledby="merge-title">
    <h2 id="merge-title">Merge into another book</h2>
    <p class="muted">
      When this is the same book as another record, merge it into that one: its editions, recipes
      and their pages, credits and tags all move there, and this record goes. Undo can't reverse a
      merge, so check what moves first.
    </p>
    <label for="merge-book" class="visually-hidden">Find the other book</label>
    <input
      id="merge-book"
      v-model="query"
      class="merge-search"
      type="search"
      maxlength="200"
      placeholder="Find the other book by title or author"
      autocomplete="off"
    />
    <OptionList
      v-slot="{ option: c }"
      :options="chosen ? [] : candidates"
      for="merge-book"
      @pick="choose"
    >
      {{ c.title }}
      <span v-if="c.authors?.length" class="page-ref">{{ c.authors.join(", ") }}</span>
    </OptionList>
    <div v-if="chosen" class="notice">
      <p>
        Merge “{{ title }}” into <a :href="`/sources/${chosen.id}`">“{{ chosen.title }}”</a>?
      </p>
      <p v-if="plan">
        It moves {{ plan.editions }} edition{{ plan.editions === 1 ? "" : "s" }},
        {{ plan.recipes }} recipe{{ plan.recipes === 1 ? "" : "s" }} and
        {{ plan.credits }} credit{{ plan.credits === 1 ? "" : "s" }} (one per person and role).
      </p>
      <p v-if="plan?.same_titles.length" class="error">
        Both have {{ plan.same_titles.length === 1 ? "a recipe" : "recipes" }} called
        {{ plan.same_titles.map((t) => `“${t}”`).join(", ") }}: likely the same recipe twice,
        which stays as two after merging.
      </p>
      <div class="row-actions">
        <button type="button" class="primary" :disabled="busy || !plan" @click="merge">
          {{ busy ? "Merging…" : "Merge" }}
        </button>
        <button type="button" class="secondary" :disabled="busy" @click="(chosen = null), (plan = null)">
          Choose another
        </button>
      </div>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </section>
</template>
