<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { type OnShelf, type OtherShelf, onShelf, putOnShelf, takeOffShelf } from "../shelf";
import PillToggle from "./PillToggle.vue";

// A book's "I have this book" (routers/shelf.py): a pill toggle (Ray's
// cleanup pass, 2026-11-11), pressed when it's on your shelf; with several
// editions, when the one shown is the one you have. Shelves shared with you
// say whether it's on them; those you may change take it too.
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
const said = ref("");
const several = computed(() => props.editions.length > 1);
const label = (editionId: string | null) =>
  props.editions.find((e) => e.id === editionId)?.label ?? null;
const name = (o: OtherShelf) => `${o.owner_name ?? "Someone"}'s shelf`;
const theirs = computed(() => (state.value?.others ?? []).filter((o) => o.on_shelf));
const addable = computed(() =>
  (state.value?.others ?? []).filter((o) => !o.on_shelf && o.editable),
);
// Of several editions, another than the one shown is the one you have.
const another = computed(
  () =>
    several.value &&
    !!state.value?.on_shelf &&
    !!state.value.edition_id &&
    state.value.edition_id !== props.shown,
);
const pressed = computed(() => !!state.value?.on_shelf && !another.value);

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

async function act(job: () => Promise<OnShelf | void>, done: string) {
  busy.value = true;
  error.value = "";
  said.value = "";
  try {
    state.value = (await job()) ?? (await onShelf(props.sourceId));
    said.value = done;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

// One edition is the one owned; of several, the one shown.
const edition = () => (several.value ? props.shown : (props.editions[0]?.id ?? null));
function toggle() {
  if (pressed.value) act(() => takeOffShelf(props.sourceId), "Taken off your shelf");
  else act(() => putOnShelf(props.sourceId, edition()), "On your shelf");
}
const add = (o: OtherShelf) =>
  act(() => putOnShelf(props.sourceId, edition(), o.owner_id), `On ${name(o)}`);
const remove = (o: OtherShelf) =>
  act(() => takeOffShelf(props.sourceId, o.owner_id), `Taken off ${name(o)}`);
</script>

<template>
  <div v-if="state" class="shelf-button">
    <PillToggle :pressed="pressed" icon="check" :disabled="busy" @toggle="toggle">
      {{ several ? "I have this edition" : "I have this book" }}
    </PillToggle>
    <p v-if="state.on_shelf" class="muted shelf-state">
      On <a href="/shelf">your shelf</a
      ><template v-if="several && label(state.edition_id)">: {{ label(state.edition_id) }}</template
      >.
    </p>
    <ul v-if="theirs.length || addable.length" class="shelf-others muted">
      <li v-for="o in theirs" :key="o.owner_id">
        On <a href="/shelf">{{ name(o) }}</a
        ><template v-if="several && label(o.edition_id)">: {{ label(o.edition_id) }}</template
        >.
        <button
          v-if="o.editable"
          type="button"
          class="link"
          :disabled="busy"
          :aria-label="`Take it off ${name(o)}`"
          @click="remove(o)"
        >
          Take it off
        </button>
      </li>
      <li v-for="o in addable" :key="o.owner_id">
        <button type="button" class="link" :disabled="busy" @click="add(o)">
          Put it on {{ name(o) }}
        </button>
      </li>
    </ul>
    <p class="visually-hidden" aria-live="polite">{{ said }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.shelf-button {
  margin: 0.5rem 0 0.75rem;
}
.shelf-button p {
  margin: 0.3rem 0 0;
}
.shelf-state,
.shelf-others {
  font-size: var(--text-sm);
}
.shelf-others {
  list-style: none;
  padding: 0;
  margin: 0.3rem 0 0;
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
