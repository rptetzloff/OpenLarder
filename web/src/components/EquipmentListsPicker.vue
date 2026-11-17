<script setup lang="ts">
import { dropLastOn } from "../chips";
import { computed, onMounted, ref } from "vue";
import OptionList from "./OptionList.vue";
import { type Item, type Lists, loadLists } from "../equipmentLists";

// Your equipment on the search page: which lists to keep the search to,
// and only some things on them or all but some. LarderPicker.vue over
// again, with its classes (*Ray, 2026-11-16: "Named lists, like the
// larder"*). It's under "More options", behind "Only what I have the
// equipment for", which ticks every list; the page is told the lists
// there are, so it knows whether to offer that.
const lists = defineModel<string[]>("lists", { required: true });
const only = defineModel<string[]>("only", { required: true });
const leaveOut = defineModel<string[]>("leaveOut", { required: true });
const props = defineProps<{ counted?: number | null; tickAll?: boolean }>();
const emit = defineEmits<{ change: []; loaded: [lists: string[]] }>();

const mine = ref<Lists | null>(null);
const findOnly = ref("");
const findOut = ref("");

onMounted(async () => {
  mine.value = await loadLists().catch(() => null);
  emit("loaded", mine.value?.lists.map((l) => l.id) ?? []);
  // A link's equipment=mine: every list.
  if (props.tickAll && mine.value && !lists.value.length && !only.value.length) {
    lists.value = mine.value.lists.map((l) => l.id);
    emit("change");
  }
});

// Things that can count: matched, and had.
const counts = (i: Item) => !!i.equipment_id && i.state === "have";
const usable = computed<Item[]>(() => (mine.value?.lists ?? []).flatMap((l) => l.items.filter(counts)));
const byId = computed(() => new Map(usable.value.map((i) => [i.id, i])));
const inTicked = computed(() => usable.value.filter((i) => lists.value.includes(i.list_id)));

function matches(find: string, from: Item[], taken: string[]) {
  const q = find.trim().toLowerCase();
  if (!q) return [];
  return from
    .filter(
      (i) =>
        !taken.includes(i.id) &&
        (i.name.toLowerCase().includes(q) || (i.equipment ?? "").toLowerCase().includes(q)),
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
  <fieldset class="larder-picker equipment-picker">
    <legend>Equipment lists</legend>
    <p v-if="mine && !mine.lists.length" class="help">
      <a href="/equipment/mine">Make a list of your equipment</a>, and keep a search to what you
      have it for here.
    </p>
    <template v-else-if="mine">
      <div class="larder-picker-lists">
        <label v-for="l in mine.lists" :key="l.id" class="check">
          <input
            type="checkbox"
            :checked="lists.includes(l.id)"
            @change="toggleList(l.id, ($event.target as HTMLInputElement).checked)"
          />
          {{ l.name }}
          <span class="muted">{{ l.items.filter(counts).length }}</span>
        </label>
      </div>

      <label for="kit-only" class="larder-picker-label">Only these things (optional)</label>
      <div class="chip-input">
        <span v-for="id in only" :key="id" class="chip">
          {{ label(id) }}
          <button type="button" class="remove" :aria-label="`Remove ${label(id)}`" @click="drop('only', id)">×</button>
        </span>
        <input
          id="kit-only"
          v-model="findOnly"
          type="search"
          autocomplete="off"
          placeholder="Find something on your lists"
          @keydown="dropLastOn($event, only, (id) => drop('only', id))"
          @keydown.enter.prevent="onlySuggestions[0] && pick('only', onlySuggestions[0])"
        />
      </div>
      <OptionList
        v-slot="{ option: i }"
        :options="onlySuggestions"
        for="kit-only"
        @pick="(i) => pick('only', i)"
      >
        {{ i.name }} <span class="page-ref">{{ i.equipment }}</span>
      </OptionList>

      <label for="kit-out" class="larder-picker-label">Leave out (optional)</label>
      <div class="chip-input">
        <span v-for="id in leaveOut" :key="id" class="chip chip-unwanted">
          {{ label(id) }}
          <button type="button" class="remove" :aria-label="`Remove ${label(id)}`" @click="drop('out', id)">×</button>
        </span>
        <input
          id="kit-out"
          v-model="findOut"
          type="search"
          autocomplete="off"
          placeholder="Something to do without in this search"
          @keydown="dropLastOn($event, leaveOut, (id) => drop('out', id))"
          @keydown.enter.prevent="outSuggestions[0] && pick('out', outSuggestions[0])"
        />
      </div>
      <OptionList
        v-slot="{ option: i }"
        :options="outSuggestions"
        for="kit-out"
        @pick="(i) => pick('out', i)"
      >
        {{ i.name }} <span class="page-ref">{{ i.equipment }}</span>
      </OptionList>

      <p class="help">
        <template v-if="inUse && counted != null">
          {{ counted.toLocaleString() }} {{ counted === 1 ? "thing counts" : "things count" }},
          each as itself and what it counts as: a stand mixer is a mixer too.
        </template>
        <template v-else>Check a list to keep the search to what's on it.</template>
        Things you want don't count. <a href="/equipment/mine">Your equipment</a>
      </p>
    </template>
  </fieldset>
</template>
