<script setup lang="ts">
import { onMounted, ref } from "vue";
import { type Book, type BookIn, KIND_NAMES, proposeBookChange, saveBook } from "../books";

// With propose, the edit is sent as a suggestion for a moderator to apply
// (routers/proposals.py), for a contributor and a published source.
const props = defineProps<{ id: string; propose?: boolean }>();
const reason = ref("");

const ROLES = ["author", "editor", "contributor", "photographer", "illustrator", "translator"];

const book = ref<Book | null>(null);
const form = ref<BookIn | null>(null);
// Years as typed, so a half-typed one doesn't jump about.
const years = ref<string[]>([]);
const error = ref("");
const saving = ref(false);
const loadFailed = ref(false);

onMounted(async () => {
  try {
    const res = await fetch(`/api/sources/${props.id}`);
    if (!res.ok) throw new Error();
    const b: Book = await res.json();
    book.value = b;
    form.value = {
      title: b.title,
      subtitle: b.subtitle ?? "",
      credits: b.credits.map((c) => ({ author_id: c.author_id, name: c.credited_as, role: c.role })),
      editions: b.editions.map((e) => ({
        id: e.id,
        title: e.title ?? "",
        publisher: e.publisher ?? "",
        published_year: e.published_year,
      })),
      // Only a website's is sent.
      paywalled: b.kind === "website" ? b.paywalled : undefined,
    };
    years.value = b.editions.map((e) => (e.published_year ? String(e.published_year) : ""));
    document.title = `Edit · ${b.title} · OpenLarder`;
  } catch {
    loadFailed.value = true;
  }
});

function move(i: number, by: number) {
  const credits = form.value!.credits;
  const [credit] = credits.splice(i, 1);
  credits.splice(i + by, 0, credit);
}

async function save() {
  if (!form.value) return;
  error.value = "";
  const editions = form.value.editions.map((e, i) => ({
    ...e,
    published_year: years.value[i].trim() ? Number(years.value[i]) : null,
  }));
  if (editions.some((e) => e.published_year !== null && !Number.isInteger(e.published_year))) {
    error.value = "A year is a number, like 2019.";
    return;
  }
  saving.value = true;
  try {
    if (props.propose) {
      await proposeBookChange(props.id, {
        ...form.value,
        editions,
        reason: reason.value.trim() || null,
      });
      location.href = `/sources/${props.id}?proposed=1`;
      return;
    }
    await saveBook(props.id, { ...form.value, editions });
    location.href = `/sources/${props.id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    saving.value = false;
  }
}
</script>

<template>
  <article>
    <p><a :href="`/sources/${id}`">← {{ book?.title ?? "Back to the book" }}</a></p>
    <h1>{{ propose ? "Suggest a change to the" : "Edit" }} {{ KIND_NAMES[book?.kind ?? "book"] }}</h1>
    <p v-if="propose" class="muted">
      A moderator sees what you'd change beside how it reads now, and applies it or says why not.
    </p>
    <p v-if="loadFailed" role="alert">This couldn't be loaded. Try reloading the page.</p>
    <form v-else-if="form && book" class="recipe-form" @submit.prevent="save">
      <label for="book-title">Title</label>
      <input id="book-title" v-model="form.title" required maxlength="300" />
      <label v-if="book.kind === 'website'" class="check"
        ><input v-model="form.paywalled" type="checkbox" /> Behind a subscription</label
      >
      <label for="book-subtitle">Subtitle</label>
      <input id="book-subtitle" v-model="form.subtitle" maxlength="500" />

      <fieldset>
        <legend>
          {{ book.kind === "website" ? "Who writes it, in order" : "Credits, in the order the book prints them" }}
        </legend>
        <p class="help">
          Names as the {{ book.kind === "website" ? "site gives" : "cover prints" }} them. Fixing a name here fixes the author's own name too,
          unless they're on other books or come from Open Library.
        </p>
        <div v-for="(c, i) in form.credits" :key="i" class="credit-row">
          <input
            v-model="c.name"
            required
            maxlength="200"
            :aria-label="`Name ${i + 1}`"
            placeholder="Name"
          />
          <select v-model="c.role" :aria-label="`Role of ${c.name || `name ${i + 1}`}`">
            <option v-for="r in ROLES" :key="r" :value="r">{{ r }}</option>
          </select>
          <button
            type="button"
            class="link"
            :disabled="i === 0"
            :aria-label="`Move ${c.name} up`"
            @click="move(i, -1)"
          >
            ↑
          </button>
          <button
            type="button"
            class="link"
            :disabled="i === form.credits.length - 1"
            :aria-label="`Move ${c.name} down`"
            @click="move(i, 1)"
          >
            ↓
          </button>
          <button
            type="button"
            class="link"
            :aria-label="`Remove ${c.name}`"
            @click="form.credits.splice(i, 1)"
          >
            Remove
          </button>
        </div>
        <button
          type="button"
          class="link"
          @click="form.credits.push({ author_id: null, name: '', role: 'author' })"
        >
          Add a name
        </button>
      </fieldset>

      <fieldset v-for="(e, i) in form.editions" :key="e.id" class="edition-edit">
        <legend>
          Edition{{ book.editions[i].isbn13 ? ` · ISBN ${book.editions[i].isbn13}` : "" }}
        </legend>
        <label :for="`edition-title-${i}`">Title, if it differs from the book's</label>
        <input :id="`edition-title-${i}`" v-model="e.title" maxlength="300" />
        <label :for="`edition-publisher-${i}`">Publisher</label>
        <input :id="`edition-publisher-${i}`" v-model="e.publisher" maxlength="200" />
        <label :for="`edition-year-${i}`">Year published</label>
        <input
          :id="`edition-year-${i}`"
          v-model="years[i]"
          class="page-input"
          inputmode="numeric"
          maxlength="4"
          placeholder="2019"
        />
      </fieldset>

      <template v-if="propose">
        <label for="book-reason">Why (optional)</label>
        <textarea
          id="book-reason"
          v-model="reason"
          rows="2"
          maxlength="500"
          placeholder="The cover gives the subtitle"
        ></textarea>
      </template>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" class="primary" :disabled="saving">
        {{ propose ? (saving ? "Sending…" : "Send the suggestion") : saving ? "Saving…" : "Save" }}
      </button>
    </form>
    <p v-else class="status">Loading…</p>
  </article>
</template>
