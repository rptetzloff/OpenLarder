<script setup lang="ts">
import { dropLastOn } from "../chips";
import { computed, onMounted, ref } from "vue";
import OptionList from "./OptionList.vue";
import { type Item, type Larder, loadLarder } from "../larder";

// "From my larder" on the search page: which lists to search with, and,
// for a big pantry, only some things in them or all but some. *Ray,
// 2026-11-10.* The search counts each thing as itself and what's above it.
const lists = defineModel<string[]>("lists", { required: true });
const only = defineModel<string[]>("only", { required: true });
const leaveOut = defineModel<string[]>("leaveOut", { required: true });
const props = defineProps<{ counted?: number | null; tickAll?: boolean }>();
const emit = defineEmits<{ change: [] }>();

const larder = ref<Larder | null>(null);
const findOnly = ref("");
const findOut = ref("");

onMounted(async () => {
  larder.value = await loadLarder().catch(() => null);
  // An older link's larder=1: every list.
  if (props.tickAll && larder.value && !lists.value.length && !only.value.length) {
    lists.value = larder.value.lists.map((l) => l.id);
    emit("change");
  }
});

// Things that can count: matched, and not out.
const usable = computed<Item[]>(() =>
  (larder.value?.lists ?? []).flatMap((l) =>
    l.items.filter((i) => i.ingredient_id && i.state !== "out"),
  ),
);
const byId = computed(() => new Map(usable.value.map((i) => [i.id, i])));
const inTicked = computed(() => usable.value.filter((i) => lists.value.includes(i.list_id)));

function matches(find: string, from: Item[], taken: string[]) {
  const q = find.trim().toLowerCase();
  if (!q) return [];
  return from
    .filter(
      (i) =>
        !taken.includes(i.id) &&
        (i.name.toLowerCase().includes(q) || (i.ingredient ?? "").toLowerCase().includes(q)),
    )
    .slice(0, 8);
}
const onlySuggestions = computed(() => matches(findOnly.value, usable.value, only.value));
const outSuggestions = computed(() =>
  matches(findOut.value, lists.value.length ? inTicked.value : usable.value, leaveOut.value),
);

function toggleList(id: string, on: boolean) {
  lists.value = on ? [...lists.value, id] : lists.value.filter((l) => l !== id);
  emit("change");
}
function pick(which: "only" | "out", item: Item) {
  if (which === "only") {
    only.value = [...only.value, item.id];
    findOnly.value = "";
  } else {
    leaveOut.value = [...leaveOut.value, item.id];
    findOut.value = "";
  }
  emit("change");
}
function drop(which: "only" | "out", id: string) {
  if (which === "only") only.value = only.value.filter((i) => i !== id);
  else leaveOut.value = leaveOut.value.filter((i) => i !== id);
  emit("change");
}
const label = (id: string) => byId.value.get(id)?.name ?? "something gone";
const inUse = computed(() => !!lists.value.length || !!only.value.length);
</script>

<template>
  <fieldset class="larder-picker">
    <legend>From my larder</legend>
    <p v-if="larder && !larder.lists.length" class="help">
      <a href="/larder">Make a larder</a> of what you have, and search with it here.
    </p>
    <template v-else-if="larder">
      <div class="larder-picker-lists">
        <label v-for="l in larder.lists" :key="l.id" class="check">
          <input
            type="checkbox"
            :checked="lists.includes(l.id)"
            @change="toggleList(l.id, ($event.target as HTMLInputElement).checked)"
          />
          {{ l.name }}
          <span class="muted">{{ l.items.filter((i) => i.ingredient_id && i.state !== "out").length }}</span>
        </label>
      </div>

      <label for="larder-only" class="larder-picker-label">Only these things (optional)</label>
      <div class="chip-input">
        <span v-for="id in only" :key="id" class="chip">
          {{ label(id) }}
          <button type="button" class="remove" :aria-label="`Remove ${label(id)}`" @click="drop('only', id)">×</button>
        </span>
        <input
          id="larder-only"
          v-model="findOnly"
          type="search"
          autocomplete="off"
          placeholder="Find something in your larder"
          @keydown="dropLastOn($event, only, (id) => drop('only', id))"
          @keydown.enter.prevent="onlySuggestions[0] && pick('only', onlySuggestions[0])"
        />
      </div>
      <OptionList
        v-slot="{ option: i }"
        :options="onlySuggestions"
        for="larder-only"
        @pick="(i) => pick('only', i)"
      >
        {{ i.name }} <span class="page-ref">{{ i.ingredient }}</span>
      </OptionList>

      <label for="larder-out" class="larder-picker-label">Leave out (optional)</label>
      <div class="chip-input">
        <span v-for="id in leaveOut" :key="id" class="chip chip-unwanted">
          {{ label(id) }}
          <button type="button" class="remove" :aria-label="`Remove ${label(id)}`" @click="drop('out', id)">×</button>
        </span>
        <input
          id="larder-out"
          v-model="findOut"
          type="search"
          autocomplete="off"
          placeholder="Something to keep out of this search"
          @keydown="dropLastOn($event, leaveOut, (id) => drop('out', id))"
          @keydown.enter.prevent="outSuggestions[0] && pick('out', outSuggestions[0])"
        />
      </div>
      <OptionList
        v-slot="{ option: i }"
        :options="outSuggestions"
        for="larder-out"
        @pick="(i) => pick('out', i)"
      >
        {{ i.name }} <span class="page-ref">{{ i.ingredient }}</span>
      </OptionList>

      <p class="help">
        <template v-if="inUse && counted != null">
          {{ counted.toLocaleString() }} {{ counted === 1 ? "thing counts" : "things count" }},
          each as itself and what's above it: chipotle hot sauce is hot sauce too.
        </template>
        <template v-else>Tick a list to search with what's on it.</template>
        Things you're out of don't count. <a href="/larder">Your larder</a>
      </p>
    </template>
  </fieldset>
</template>
