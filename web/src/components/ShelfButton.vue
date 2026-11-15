<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { type OnShelf, type OtherShelf, onShelf, putOnShelf, takeOffShelf } from "../shelf";
import PillToggle from "./PillToggle.vue";

// A book's "I have this book" (routers/shelf.py): a pill toggle (Ray's
// cleanup pass, 2026-11-11), pressed when it's on your shelf; with several
// editions, when the one shown is the one you have. Shelves shared with you
// say whether it's on them; those you may change take it too.
//
// And "I want this book" beside it (Ray, 2026-11-14): a second state of
// the shelf. A book is had or wanted, never both, so pressing one lets go
// of the other, and the one for wanting isn't there for a book you have.
const props = defineProps<{
  sourceId: string;
  // The book's editions, labelled as the page labels them.
  editions: { id: string; label: string }[];
  // The edition the page shows.
  shown: string | null;
}>();
// The edition on your shelf, or a shelf shared with you, once known, for
// the page to show; and whether you want the book, for the page to put
// where to buy it first.
const emit = defineEmits<{ mine: [editionId: string]; wanted: [yes: boolean] }>();

const state = ref<OnShelf | null>(null);
const busy = ref(false);
const error = ref("");
const said = ref("");
const several = computed(() => props.editions.length > 1);
const label = (editionId: string | null) =>
  props.editions.find((e) => e.id === editionId)?.label ?? null;
const name = (o: OtherShelf) => `${o.owner_name ?? "Someone"}'s shelf`;
const who = (o: OtherShelf) => o.owner_name ?? "Someone";
// Theirs to see: the book on a shelf shared with you, had or wanted.
const theirs = computed(() => (state.value?.others ?? []).filter((o) => o.on_shelf || o.wanted));
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

function took(now: OnShelf) {
  state.value = now;
  emit("wanted", now.wanted);
}

onMounted(async () => {
  try {
    took(await onShelf(props.sourceId));
    const edition =
      state.value!.edition_id ?? state.value!.others.find((o) => o.edition_id)?.edition_id;
    if (edition) emit("mine", edition);
  } catch {
    // Shown as not on the shelf; adding says what's wrong.
    state.value = {
      source_id: props.sourceId,
      on_shelf: false,
      wanted: false,
      edition_id: null,
      others: [],
    };
  }
});

async function act(job: () => Promise<OnShelf | void>, done: string) {
  // A press while the last one is still being saved does nothing. The
  // pills aren't disabled for it: a button that's disabled while it has
  // focus loses it, and whoever pressed it by keyboard is back at the top
  // of the page.
  if (busy.value) return;
  busy.value = true;
  error.value = "";
  said.value = "";
  try {
    took((await job()) ?? (await onShelf(props.sourceId)));
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
function toggleWant() {
  if (state.value?.wanted) act(() => takeOffShelf(props.sourceId), "No longer a book you want");
  else
    act(
      () => putOnShelf(props.sourceId, null, undefined, "want"),
      "On your shelf, as a book you want",
    );
}
const add = (o: OtherShelf) =>
  act(() => putOnShelf(props.sourceId, edition(), o.owner_id), `On ${name(o)}`);
const remove = (o: OtherShelf) =>
  act(() => takeOffShelf(props.sourceId, o.owner_id), `Taken off ${name(o)}`);
</script>

<template>
  <div v-if="state" class="shelf-button">
    <div class="shelf-pills">
      <PillToggle :pressed="pressed" icon="check" @toggle="toggle">
        {{ several ? "I have this edition" : "I have this book" }}
      </PillToggle>
      <!-- Not for a book you have: you don't want what's on the shelf. -->
      <PillToggle
        v-if="!state.on_shelf"
        :pressed="state.wanted"
        icon="bookmark"
        @toggle="toggleWant"
      >
        I want this book
      </PillToggle>
    </div>
    <p v-if="state.on_shelf" class="muted shelf-state">
      On <a href="/shelf">your shelf</a
      ><template v-if="several && label(state.edition_id)">: {{ label(state.edition_id) }}</template
      >.
    </p>
    <p v-else-if="state.wanted" class="muted shelf-state">
      On <a href="/shelf">your shelf</a>, as a book you want.
    </p>
    <ul v-if="theirs.length || addable.length" class="shelf-others muted">
      <li v-for="o in theirs" :key="o.owner_id">
        <template v-if="o.wanted">
          {{ who(o) }} wants it: it's on <a href="/shelf">{{ name(o) }}</a
          >.
        </template>
        <template v-else>
          On <a href="/shelf">{{ name(o) }}</a
          ><template v-if="several && label(o.edition_id)">: {{ label(o.edition_id) }}</template
          >.
        </template>
        <button
          v-if="o.editable"
          type="button"
          class="secondary small"
          :disabled="busy"
          :aria-label="`Take it off ${name(o)}`"
          @click="remove(o)"
        >
          Take it off
        </button>
      </li>
      <li v-for="o in addable" :key="`add-${o.owner_id}`">
        <button type="button" class="secondary small" :disabled="busy" @click="add(o)">
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
.shelf-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
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
.shelf-others button {
  margin-left: 0.35rem;
}
.shelf-others li > button:first-child {
  margin-left: 0;
}
</style>
