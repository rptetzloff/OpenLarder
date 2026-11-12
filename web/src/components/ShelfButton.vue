<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { type OnShelf, onShelf, putOnShelf, takeOffShelf } from "../shelf";

// A book's "I have this book" (routers/shelf.py): on your shelf, with the
// edition you have when it has several, so its recipes open at your page.
const props = defineProps<{
  sourceId: string;
  // The book's editions, labelled as the page labels them.
  editions: { id: string; label: string }[];
  // The edition the page shows.
  shown: string | null;
}>();
// The edition on your shelf, once known, for the page to show.
const emit = defineEmits<{ mine: [editionId: string] }>();

const state = ref<OnShelf | null>(null);
const busy = ref(false);
const error = ref("");
const several = computed(() => props.editions.length > 1);
const mineLabel = computed(
  () => props.editions.find((e) => e.id === state.value?.edition_id)?.label ?? null,
);

onMounted(async () => {
  try {
    state.value = await onShelf(props.sourceId);
    if (state.value.edition_id) emit("mine", state.value.edition_id);
  } catch {
    // Shown as not on the shelf; adding says what's wrong.
    state.value = { source_id: props.sourceId, on_shelf: false, edition_id: null };
  }
});

async function act(job: () => Promise<OnShelf | void>) {
  busy.value = true;
  error.value = "";
  try {
    const now = await job();
    state.value = now ?? { source_id: props.sourceId, on_shelf: false, edition_id: null };
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

// One edition is the one you have; of several, the one shown.
const edition = () => (several.value ? props.shown : (props.editions[0]?.id ?? null));
const add = () => act(() => putOnShelf(props.sourceId, edition()));
const change = () => act(() => putOnShelf(props.sourceId, props.shown));
const remove = () => act(() => takeOffShelf(props.sourceId));
</script>

<template>
  <div v-if="state" class="shelf-button">
    <template v-if="state.on_shelf">
      <p class="shelf-state">
        <span aria-hidden="true">✓</span> On <a href="/shelf">your shelf</a>.<template
          v-if="several && mineLabel"
        >
          Yours: {{ mineLabel }}.</template
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
        <button type="button" class="link" :disabled="busy" @click="remove">
          Take it off my shelf
        </button>
      </p>
    </template>
    <button v-else type="button" class="secondary" :disabled="busy" @click="add">
      {{ several ? "I have this edition" : "I have this book" }}
    </button>
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
</style>
