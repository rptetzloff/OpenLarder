<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { type OnShelf, type OtherShelf, onShelf, putOnShelf, takeOffShelf } from "../shelf";

// A book's "I have this book" (routers/shelf.py): on your shelf, with the
// edition you have when it has several, so its recipes open at your page.
// Shelves shared with you say whether it's on them; those you may change
// take it too.
const props = defineProps<{
  sourceId: string;
  // The book's editions, labelled as the page labels them.
  editions: { id: string; label: string }[];
  // The edition the page shows.
  shown: string | null;
}>();
// The edition on your shelf, or a shelf shared with you, once known, for
// the page to show.
const emit = defineEmits<{ mine: [editionId: string] }>();

const state = ref<OnShelf | null>(null);
const busy = ref(false);
const error = ref("");
const several = computed(() => props.editions.length > 1);
const label = (editionId: string | null) =>
  props.editions.find((e) => e.id === editionId)?.label ?? null;
const name = (o: OtherShelf) => `${o.owner_name ?? "Someone"}'s shelf`;
const theirs = computed(() => (state.value?.others ?? []).filter((o) => o.on_shelf));
const addable = computed(() =>
  (state.value?.others ?? []).filter((o) => !o.on_shelf && o.editable),
);

onMounted(async () => {
  try {
    state.value = await onShelf(props.sourceId);
    const edition =
      state.value.edition_id ?? state.value.others.find((o) => o.edition_id)?.edition_id;
    if (edition) emit("mine", edition);
  } catch {
    // Shown as not on the shelf; adding says what's wrong.
    state.value = { source_id: props.sourceId, on_shelf: false, edition_id: null, others: [] };
  }
});

async function act(job: () => Promise<OnShelf | void>) {
  busy.value = true;
  error.value = "";
  try {
    state.value = (await job()) ?? (await onShelf(props.sourceId));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

// One edition is the one owned; of several, the one shown.
const edition = () => (several.value ? props.shown : (props.editions[0]?.id ?? null));
const add = (owner?: string) => act(() => putOnShelf(props.sourceId, edition(), owner));
const change = () => act(() => putOnShelf(props.sourceId, props.shown));
const remove = (owner?: string) => act(() => takeOffShelf(props.sourceId, owner));
</script>

<template>
  <div v-if="state" class="shelf-button">
    <template v-if="state.on_shelf">
      <p class="shelf-state">
        <span aria-hidden="true">✓</span> On <a href="/shelf">your shelf</a>.<template
          v-if="several && label(state.edition_id)"
        >
          Yours: {{ label(state.edition_id) }}.</template
        >
      </p>
      <p class="shelf-actions">
        <button
          v-if="several && shown && shown !== state.edition_id"
          type="button"
          class="link"
          :disabled="busy"
          @click="change"
        >
          I have this edition instead
        </button>
        <button type="button" class="link" :disabled="busy" @click="remove()">
          Take it off my shelf
        </button>
      </p>
    </template>
    <button v-else type="button" class="secondary" :disabled="busy" @click="add()">
      {{ several ? "I have this edition" : "I have this book" }}
    </button>
    <ul v-if="theirs.length || addable.length" class="shelf-others">
      <li v-for="o in theirs" :key="o.owner_id">
        <span aria-hidden="true">✓</span> On <a href="/shelf">{{ name(o) }}</a
        >.<template v-if="several && label(o.edition_id)"> Theirs: {{ label(o.edition_id) }}.</template>
        <button
          v-if="o.editable"
          type="button"
          class="link"
          :disabled="busy"
          :aria-label="`Take it off ${name(o)}`"
          @click="remove(o.owner_id)"
        >
          Take it off
        </button>
      </li>
      <li v-for="o in addable" :key="o.owner_id">
        <button type="button" class="link" :disabled="busy" @click="add(o.owner_id)">
          Put it on {{ name(o) }}
        </button>
      </li>
    </ul>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.shelf-button {
  margin: 0.5rem 0 0.75rem;
}
.shelf-button p {
  margin: 0;
}
.shelf-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
}
.shelf-others {
  list-style: none;
  padding: 0;
  margin: 0.35rem 0 0;
  display: grid;
  gap: 0.2rem;
}
.shelf-others .link {
  margin-left: 0.35rem;
}
.shelf-others li > .link:first-child {
  margin-left: 0;
}
</style>
