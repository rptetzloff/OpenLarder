<script setup lang="ts">
import { ref } from "vue";
import { type Book, type LinkPreview, linkToOpenLibrary, previewLink } from "../books";

// Links a book that came in without an Open Library match to its record
// there. Shows what Open Library has and what linking would change, and
// links only once that's confirmed: other books share titles.
const props = defineProps<{ book: Book }>();

const reference = ref("");
const preview = ref<LinkPreview | null>(null);
const error = ref("");
const busy = ref(false);

const OUTCOMES: Record<string, string> = {
  linked: "already linked",
  link: "will be linked",
  add: "will be added as an author",
  unmatched: "isn't credited on this book here, so it won't be added",
};

async function look() {
  busy.value = true;
  error.value = "";
  preview.value = null;
  try {
    preview.value = await previewLink(props.book.id, reference.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function link() {
  busy.value = true;
  error.value = "";
  try {
    await linkToOpenLibrary(props.book.id, reference.value);
    location.reload();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    busy.value = false;
  }
}
</script>

<template>
  <section class="ol-link">
    <h2>Link to Open Library</h2>
    <p class="status">
      This book isn't linked to Open Library, so another printing added by ISBN would arrive as a
      separate book. Give the ISBN of a printing Open Library has, or a link to its page.
    </p>
    <form class="isbn-form" @submit.prevent="look">
      <label for="ol-reference">ISBN or Open Library link</label>
      <div class="row">
        <input
          id="ol-reference"
          v-model="reference"
          autocomplete="off"
          placeholder="https://openlibrary.org/works/OL21362065W"
          required
          @input="preview = null"
        />
        <button type="submit" class="primary" :disabled="busy">
          {{ busy && !preview ? "Looking…" : "Look up" }}
        </button>
      </div>
    </form>

    <div v-if="preview" class="ol-preview">
      <p>
        Open Library has
        <a v-if="preview.open_library_url" :href="preview.open_library_url">
          <strong>{{ preview.title }}</strong></a
        ><strong v-else>{{ preview.title }}</strong
        ><span v-if="preview.subtitle">: {{ preview.subtitle }}</span>.
      </p>
      <p v-if="preview.problem" class="error" role="alert">{{ preview.problem }}</p>
      <template v-else>
        <p>Check it's the same book. Linking will:</p>
        <ul>
          <li>link “{{ book.title }}” to that Open Library work, keeping its title here;</li>
          <li v-if="preview.edition">
            <template v-if="preview.edition.step === 'fill'">
              fill in what's blank on the edition here with ISBN {{ preview.edition.fills_isbn13 }}
              from
            </template>
            <template v-else>add another edition: </template>
            <a :href="preview.edition.open_library_url">{{
              [preview.edition.publisher, preview.edition.published_year].filter(Boolean).join(", ") ||
              "Open Library's edition"
            }}</a
            ><span v-if="preview.edition.isbn13 && preview.edition.step === 'add'">
              , ISBN {{ preview.edition.isbn13 }}</span
            >;
          </li>
          <li v-for="a in preview.authors" :key="a.open_library_url">
            <a :href="a.open_library_url">{{ a.name }}</a>
            <span v-if="a.credited_as && a.credited_as !== a.name">
              (credited here as “{{ a.credited_as }}”)</span
            >
            {{ OUTCOMES[a.outcome] }};
          </li>
          <li>leave the recipes and their pages as they are.</li>
        </ul>
        <div class="admin-actions">
          <button type="button" class="primary" :disabled="busy" @click="link">
            {{ busy ? "Linking…" : "Link" }}
          </button>
          <button type="button" class="link" :disabled="busy" @click="preview = null">Cancel</button>
        </div>
      </template>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </section>
</template>
