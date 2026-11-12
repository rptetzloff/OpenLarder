<script setup lang="ts">
import { onMounted, ref } from "vue";
import { MAX_NOTE, type Notes, recipeNotes, removeNote, writeNote } from "../notes";

// Your note on a recipe, and the notes on it shared with you
// (routers/notes.py). Ray, 2026-11-11: "notes.... that are kept personal
// (or shared)". Yours alone unless you tick a group.
const props = defineProps<{ recipeId: string }>();

const notes = ref<Notes | null>(null);
const editing = ref(false);
const draft = ref("");
const picked = ref<string[]>([]);
const busy = ref(false);
const error = ref("");

onMounted(async () => {
  try {
    notes.value = await recipeNotes(props.recipeId);
  } catch {
    // No notes shown.
  }
});

function start() {
  draft.value = notes.value?.mine?.body ?? "";
  picked.value = (notes.value?.mine?.shared_with ?? []).map((g) => g.id);
  error.value = "";
  editing.value = true;
}

async function act(job: () => Promise<Notes | void>) {
  busy.value = true;
  error.value = "";
  try {
    notes.value = (await job()) ?? (await recipeNotes(props.recipeId));
    editing.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

const save = () => act(() => writeNote(props.recipeId, draft.value, picked.value));
const remove = () => act(() => removeNote(props.recipeId));
const when = (at: string) =>
  new Date(at).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
</script>

<template>
  <section v-if="notes" class="recipe-section recipe-notes" aria-labelledby="notes-title">
    <div class="table-head">
      <h2 id="notes-title">Notes</h2>
      <button v-if="!editing" type="button" class="secondary small" @click="start">
        {{ notes.mine ? "Change my note" : "+ Add a note" }}
      </button>
    </div>
    <form v-if="editing" class="note-form" @submit.prevent="save">
      <label for="note-body">Your note</label>
      <textarea
        id="note-body"
        v-model="draft"
        rows="4"
        :maxlength="MAX_NOTE"
        aria-describedby="note-help"
        required
      ></textarea>
      <p id="note-help" class="help">
        Your own words: what you changed, what you'd do next time. Please don't copy the recipe's
        amounts or method here. Only you see it, unless you tick a group.
      </p>
      <fieldset v-if="notes.groups.length" class="larder-share">
        <legend>Who else sees it</legend>
        <label v-for="g in notes.groups" :key="g.id" class="check">
          <input v-model="picked" type="checkbox" :value="g.id" /> {{ g.name }}
        </label>
      </fieldset>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="note-actions">
        <button type="submit" class="primary small" :disabled="busy || !draft.trim()">
          {{ busy ? "Saving…" : "Save" }}
        </button>
        <button type="button" class="secondary small" :disabled="busy" @click="editing = false">
          Cancel
        </button>
        <button v-if="notes.mine" type="button" class="secondary small" :disabled="busy" @click="remove">
          Delete my note
        </button>
      </div>
    </form>
    <div v-else-if="notes.mine" class="note">
      <p class="note-body">{{ notes.mine.body }}</p>
      <p class="muted note-meta">
        {{
          notes.mine.shared_with.length
            ? `Yours, shared with ${notes.mine.shared_with.map((g) => g.name).join(", ")}`
            : "Only you see this"
        }}
        · {{ when(notes.mine.updated_at) }}
      </p>
    </div>
    <p v-else-if="!notes.others.length" class="status">
      Nothing yet. A note is yours alone unless you share it with a group.
    </p>
    <div v-for="(n, i) in notes.others" :key="i" class="note">
      <p class="note-body">{{ n.body }}</p>
      <p class="muted note-meta">
        {{ n.author ?? "Someone" }}, through {{ n.through.map((g) => g.name).join(", ") }} ·
        {{ when(n.updated_at) }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.note {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0.625rem 0.875rem;
  margin-bottom: 0.5rem;
}
.note p {
  margin: 0;
}
.note-body {
  white-space: pre-line;
  overflow-wrap: anywhere;
}
.note-meta {
  font-size: 0.875rem;
  margin-top: 0.25rem;
}
.note-form label[for="note-body"] {
  display: block;
  font-weight: 600;
  margin-bottom: 0.3rem;
}
.note-form textarea {
  font: inherit;
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  box-sizing: border-box;
  width: 100%;
}
.note-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}
</style>
