<script setup lang="ts">
import { computed, ref, watch } from "vue";
import IngredientPicker from "../components/IngredientPicker.vue";
import type { Named } from "../ingredients";
import {
  type Item,
  type Larder,
  type List,
  STATES,
  type State,
  addItem,
  addList,
  changeItem,
  loadLarder,
  removeItem,
  removeList,
  renameList,
} from "../larder";
import type { Me } from "../me";

// Your larder: lists of what you have, your way ("Pantry", "Spice drawer"),
// each thing matched to an ingredient so search can use it. *Ray,
// 2026-11-08 and 2026-11-10.*
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Your larder · OpenLarder";

const larder = ref<Larder | null>(null);
const error = ref("");
const busy = ref(false);
const newList = ref("");
const adding = ref<Record<string, string>>({});
// The item whose ingredient is being chosen.
const choosing = ref<string | null>(null);
const total = computed(() =>
  (larder.value?.lists ?? []).reduce((n, l) => n + l.items.length, 0),
);

async function act(work: () => Promise<unknown>) {
  busy.value = true;
  error.value = "";
  try {
    await work();
    larder.value = await loadLarder();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

function makeList() {
  const name = newList.value.trim();
  if (!name) return;
  act(async () => {
    await addList(name);
    newList.value = "";
  });
}

function add(list: List) {
  const name = (adding.value[list.id] ?? "").trim();
  if (!name) return;
  act(async () => {
    await addItem(list.id, name);
    adding.value[list.id] = "";
  });
}

function rename(list: List) {
  const name = prompt("The list's new name", list.name)?.trim();
  if (name && name !== list.name) act(() => renameList(list.id, name));
}

function drop(list: List) {
  const what = list.items.length ? ` and the ${list.items.length} things on it` : "";
  if (confirm(`Remove “${list.name}”${what}?`)) act(() => removeList(list.id));
}

const setState = (item: Item, state: State) => act(() => changeItem(item.id, { state }));
const move = (item: Item, listId: string) => act(() => changeItem(item.id, { list_id: listId }));
const choose = (item: Item, picked: Named) =>
  act(async () => {
    await changeItem(item.id, { ingredient_id: picked.id });
    choosing.value = null;
  });
const unmatch = (item: Item) => act(() => changeItem(item.id, { ingredient_id: "none" }));

watch(
  () => props.user,
  (user) => {
    if (user && !larder.value) act(async () => {});
  },
  { immediate: true },
);
</script>

<template>
  <article class="wide larder-page">
    <div class="list-head">
      <h1>Your larder</h1>
      <p class="muted">
        What you have, in lists of your own. Each thing is matched to an ingredient, so
        <a href="/search?larder=1">search</a> can find what you can make with it, and it counts as
        what's above it too: chipotle hot sauce is hot sauce. Only you see your larder.
      </p>
    </div>
    <p v-if="user === null" class="status">
      <a href="/api/auth/login">Sign in</a> to keep a larder.
    </p>
    <template v-else-if="user">
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="!larder" class="status">Loading…</p>
      <template v-else>
        <p v-if="total" class="status larder-summary">
          {{ larder.counted.toLocaleString() }} of {{ total.toLocaleString() }}
          {{ total === 1 ? "thing counts" : "things count" }} in a search.
          <a href="/search?larder=1" class="button-outline">What can I make?</a>
        </p>
        <div class="larder-lists">
          <section
            v-for="list in larder.lists"
            :key="list.id"
            class="tool-panel larder-list"
            :aria-labelledby="`list-${list.id}`"
          >
            <div class="larder-list-head">
              <h2 :id="`list-${list.id}`">{{ list.name }}</h2>
              <span>
                <button type="button" class="link" :disabled="busy" @click="rename(list)">
                  Rename
                </button>
                <button type="button" class="link" :disabled="busy" @click="drop(list)">
                  Remove
                </button>
              </span>
            </div>
            <form class="inline-form" @submit.prevent="add(list)">
              <label :for="`add-${list.id}`" class="visually-hidden">Add to {{ list.name }}</label>
              <input
                :id="`add-${list.id}`"
                v-model="adding[list.id]"
                maxlength="200"
                :placeholder="`Add to ${list.name}`"
                autocomplete="off"
              />
              <button type="submit" class="primary small" :disabled="busy">Add</button>
            </form>
            <ul v-if="list.items.length" class="larder-items">
              <li v-for="item in list.items" :key="item.id" :class="`state-${item.state}`">
                <div class="larder-item-name">
                  <strong>{{ item.name }}</strong>
                  <span v-if="item.ingredient" class="muted">
                    ·
                    <a :href="`/ingredients/${item.ingredient_id}`">{{ item.ingredient }}</a>
                    <button type="button" class="link" :disabled="busy" @click="unmatch(item)">
                      Not this
                    </button>
                  </span>
                  <span v-else class="muted">
                    · not matched, so search can't use it
                    <button type="button" class="link" :disabled="busy" @click="choosing = item.id">
                      Choose what it is
                    </button>
                  </span>
                </div>
                <IngredientPicker
                  v-if="choosing === item.id"
                  :input-id="`pick-${item.id}`"
                  :label="`What “${item.name}” is`"
                  placeholder="Find the ingredient"
                  :exclude="[]"
                  @pick="(p) => choose(item, p)"
                />
                <div class="larder-item-actions">
                  <div
                    class="kind-filter"
                    role="group"
                    :aria-label="`${item.name}: have, low or out`"
                  >
                    <button
                      v-for="s in STATES"
                      :key="s.state"
                      type="button"
                      class="secondary small"
                      :aria-pressed="item.state === s.state"
                      :disabled="busy"
                      @click="setState(item, s.state)"
                    >
                      {{ s.label }}
                    </button>
                  </div>
                  <label v-if="larder.lists.length > 1" class="larder-move">
                    <span class="visually-hidden">Move {{ item.name }} to</span>
                    <select
                      :value="item.list_id"
                      :disabled="busy"
                      @change="move(item, ($event.target as HTMLSelectElement).value)"
                    >
                      <option v-for="l in larder.lists" :key="l.id" :value="l.id">
                        {{ l.name }}
                      </option>
                    </select>
                  </label>
                  <button
                    type="button"
                    class="link"
                    :disabled="busy"
                    @click="act(() => removeItem(item.id))"
                  >
                    Remove
                  </button>
                </div>
              </li>
            </ul>
            <p v-else class="status">Nothing here yet.</p>
          </section>
        </div>
        <form class="inline-form larder-new" @submit.prevent="makeList">
          <label for="new-list" class="visually-hidden">A new list</label>
          <input
            id="new-list"
            v-model="newList"
            maxlength="100"
            placeholder="A new list: Pantry, Spice drawer, Freezer…"
          />
          <button type="submit" class="primary" :disabled="busy">Add the list</button>
        </form>
      </template>
    </template>
  </article>
</template>
