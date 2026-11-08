<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import type { Book } from "../books";
import { checkLines, type LineReview, type Recipe, saveRecipe } from "../recipes";

// New when bookId is given, editing when recipeId is.
const props = defineProps<{ bookId?: string; recipeId?: string }>();

const book = ref<Book | null>(null);
const title = ref("");
const ingredients = ref("");
// Per edition: is the recipe in it, and on which page.
const editions = ref<{ id: string; label: string; included: boolean; page: string }[]>([]);
const error = ref("");
const saving = ref(false);
const loadFailed = ref(false);

const example = ["rhubarb", "caster sugar", "vanilla pod"].join("\n");
const heading = computed(() => (props.recipeId ? "Edit recipe" : "Add a recipe"));

function label(e: { title: string | null; published_year: number | null; isbn13: string | null }) {
  return [e.title ?? book.value?.title, e.published_year, e.isbn13 && `ISBN ${e.isbn13}`]
    .filter(Boolean)
    .join(" · ");
}

onMounted(async () => {
  try {
    let existing: Recipe | null = null;
    let bookId = props.bookId;
    if (props.recipeId) {
      const res = await fetch(`/api/recipes/${props.recipeId}`);
      if (!res.ok) throw new Error();
      existing = await res.json();
      bookId = existing!.book.id;
    }
    const res = await fetch(`/api/books/${bookId}`);
    if (!res.ok) throw new Error();
    book.value = await res.json();
    const pages = new Map(existing?.pages.map((p) => [p.edition_id, p.page]) ?? []);
    editions.value = book.value!.editions.map((e) => ({
      id: e.id,
      label: label(e),
      // A new recipe is assumed to be in every edition until unticked.
      included: existing ? pages.has(e.id) : true,
      page: pages.get(e.id) ?? "",
    }));
    if (existing) {
      title.value = existing.title;
      ingredients.value = existing.ingredients.join("\n");
    }
    document.title = `${heading.value} · ${book.value!.title} · OpenLarder`;
  } catch {
    loadFailed.value = true;
  }
});

// The entry rules, checked as the lines are typed (issue #26). Advice only:
// a line can be an exception, so saving never waits on it.
const reviews = ref<{ index: number; line: string; review: LineReview }[]>([]);
let asked = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
watch(ingredients, () => {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const mine = ++asked;
    const lines = ingredients.value.split("\n");
    try {
      const found = await checkLines(lines);
      if (mine !== asked) return;
      reviews.value = found
        .map((review, index) => ({ index, line: lines[index].trim(), review }))
        .filter((r) => r.review.problems.length);
    } catch {
      if (mine === asked) reviews.value = [];
    }
  }, 400);
});

// Replaces (or with null removes) a line, if it still reads as it did.
function fix(index: number, line: string, replacement: string | null) {
  const lines = ingredients.value.split("\n");
  if (lines[index]?.trim() !== line) return;
  if (replacement === null) lines.splice(index, 1);
  else lines[index] = replacement;
  ingredients.value = lines.join("\n");
}

async function save() {
  saving.value = true;
  error.value = "";
  try {
    const id = await saveRecipe(
      {
        title: title.value,
        editions: editions.value
          .filter((e) => e.included)
          .map((e) => ({ edition_id: e.id, page: e.page.trim() || null })),
        ingredients: ingredients.value.split("\n"),
      },
      props.recipeId ? { recipeId: props.recipeId } : { bookId: book.value!.id },
    );
    location.href = `/recipes/${id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    saving.value = false;
  }
}
</script>

<template>
  <article>
    <p v-if="book"><a :href="`/books/${book.id}`">← {{ book.title }}</a></p>
    <h1>{{ heading }}</h1>
    <p v-if="loadFailed" role="alert">This couldn't be loaded. Try reloading the page.</p>
    <form v-else-if="book" class="recipe-form" @submit.prevent="save">
      <label for="recipe-title">Title, as the book prints it</label>
      <input id="recipe-title" v-model="title" required maxlength="200" />

      <fieldset>
        <legend>Page</legend>
        <p class="help">Leave a page blank if you don't know it yet.</p>
        <div v-for="e in editions" :key="e.id" class="edition-row">
          <label v-if="editions.length > 1" class="check">
            <input v-model="e.included" type="checkbox" />
            {{ e.label }}
          </label>
          <span v-else class="only-edition">{{ e.label }}</span>
          <input
            v-model="e.page"
            :disabled="!e.included"
            :aria-label="`Page in ${e.label}`"
            class="page-input"
            maxlength="20"
            placeholder="112"
          />
        </div>
      </fieldset>

      <label for="recipe-ingredients">Ingredients, one per line, without amounts</label>
      <textarea
        id="recipe-ingredients"
        v-model="ingredients"
        rows="10"
        spellcheck="false"
        :placeholder="example"
        aria-describedby="recipe-ingredients-help"
      />
      <p id="recipe-ingredients-help" class="help">
        Just what goes in, as the book names it: “rhubarb”, not “200g rhubarb”. Amounts and
        the method stay in the book.
      </p>
      <ul v-if="reviews.length" class="line-hints" aria-live="polite">
        <li v-for="r in reviews" :key="`${r.index}:${r.line}`">
          <strong>{{ r.line }}</strong>: {{ r.review.problems.join(" ") }}
          <button
            v-if="r.review.suggestion"
            type="button"
            class="link"
            @click="fix(r.index, r.line, r.review.suggestion)"
          >
            Use “{{ r.review.suggestion }}”
          </button>
          <button
            v-else-if="r.review.remove"
            type="button"
            class="link"
            @click="fix(r.index, r.line, null)"
          >
            Remove it
          </button>
        </li>
      </ul>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" class="primary" :disabled="saving">
        {{ saving ? "Saving…" : "Save" }}
      </button>
    </form>
    <p v-else class="status">Loading…</p>
  </article>
</template>
