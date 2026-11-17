<script setup lang="ts">
import SignInLink from "../components/SignInLink.vue";
import { computed, ref, watch } from "vue";
import EquipmentPicker from "../components/EquipmentPicker.vue";
import type { Related } from "../equipment";
import {
  type Item,
  type List,
  type Lists,
  STATES,
  type State,
  addItem,
  addList,
  changeItem,
  loadLists,
  removeItem,
  removeList,
  renameList,
  shareList,
} from "../equipmentLists";
import type { Me } from "../me";

// Your equipment: lists of what you have and want, your way ("Kitchen",
// "Cabin"), each thing matched to a piece of equipment. The larder's page
// (LarderPage.vue) over again, with its classes: *Ray, 2026-11-16*, asked
// how his equipment spec's one checklist would be shared, "it should work
// like larder and book lists work", and of the two, "Named lists, like the
// larder". What differs is what equipment is: have or want, where a
// larder's thing is had, low or out (*Ray, 2026-11-16: "Have / Want"*).
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Your equipment · OpenLarder";

const lists = ref<Lists | null>(null);
const error = ref("");
const busy = ref(false);
const newList = ref("");
const adding = ref<Record<string, string>>({});
// The item whose piece of equipment is being chosen.
const choosing = ref<string | null>(null);
const total = computed(() => (lists.value?.lists ?? []).reduce((n, l) => n + l.items.length, 0));
// Nothing on the page: signed out, or nothing in any list shown.
const empty = computed(() => props.user === null || (!!lists.value && !total.value));

async function act(work: () => Promise<unknown>) {
  busy.value = true;
  error.value = "";
  try {
    await work();
    lists.value = await loadLists();
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
  const n = list.items.length;
  const what = n ? ` and the ${n === 1 ? "one thing" : `${n} things`} on it` : "";
  if (confirm(`Remove “${list.name}”${what}?`)) act(() => removeList(list.id));
}

const setState = (item: Item, state: State) => act(() => changeItem(item.id, { state }));
const move = (item: Item, listId: string) => act(() => changeItem(item.id, { list_id: listId }));
const choose = (item: Item, picked: Related) =>
  act(async () => {
    await changeItem(item.id, { equipment_id: picked.id });
    choosing.value = null;
  });
const unmatch = (item: Item) => act(() => changeItem(item.id, { equipment_id: "none" }));
// What counts in a search: matched, and had.
const counts = (item: Item) => !!item.equipment_id && item.state === "have";
// Things ticked to search with ("What can I make with only these?").
const ticked = ref<string[]>([]);
function tick(item: Item, on: boolean) {
  ticked.value = on ? [...ticked.value, item.id] : ticked.value.filter((i) => i !== item.id);
}
const withTicked = computed(() => `/search?${ticked.value.map((i) => `ei=${i}`).join("&")}`);
// The list whose sharing is open.
const sharing = ref<string | null>(null);
function toggleGroup(list: List, groupId: string, on: boolean) {
  const ids = new Set(list.shared_with.map((g) => g.id));
  if (on) ids.add(groupId);
  else ids.delete(groupId);
  act(() => shareList(list.id, [...ids]));
}
// The lists an item can move to: those you may change.
const movable = computed(() => (lists.value?.lists ?? []).filter((l) => l.editable));

watch(
  () => props.user,
  (user) => {
    if (user && !lists.value) act(async () => {});
  },
  { immediate: true },
);
</script>

<template>
  <article class="wide larder-page equipment-lists-page">
    <div class="list-head">
      <h1>Your equipment</h1>
      <p class="muted">
        Only you see your equipment, and the household <a href="/groups">groups</a> you share a
        list with.
      </p>
    </div>
    <!-- As the larder's page: one sentence under the heading, and the rest
         here, closed unless there's nothing on the page. -->
    <details class="how" :open="empty">
      <summary>How this works</summary>
      <p>
        What you have, in lists of your own. Each thing is matched to a piece of
        <a href="/equipment">equipment</a>, so <a href="/search?equipment=mine">search</a> can keep
        to the recipes you have the equipment for, and it counts as what that counts as too: a
        stand mixer is a mixer. Something you want stays on its list and doesn't count as one you
        have.
      </p>
    </details>
    <p v-if="user === null" class="status">
      <SignInLink /> to keep lists of your equipment.
    </p>
    <template v-else-if="user">
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="!lists" class="status">Loading…</p>
      <template v-else>
        <p v-if="total" class="status larder-summary">
          {{ lists.counted.toLocaleString() }} of {{ total.toLocaleString() }}
          {{ total === 1 ? "thing counts" : "things count" }} in a search.
          <a href="/search?equipment=mine" class="secondary">What can I make?</a>
        </p>
        <p v-if="ticked.length" class="larder-ticked" role="status">
          {{ ticked.length }} {{ ticked.length === 1 ? "thing" : "things" }} checked.
          <a :href="withTicked" class="secondary">What can I make with only these?</a>
          <button type="button" class="link" @click="ticked = []">Clear</button>
        </p>
        <div class="larder-lists">
          <section
            v-for="list in lists.lists"
            :key="list.id"
            class="tool-panel larder-list"
            :aria-labelledby="`list-${list.id}`"
          >
            <div class="larder-list-head">
              <h2 :id="`list-${list.id}`">{{ list.name }}</h2>
              <span v-if="list.mine">
                <button type="button" class="secondary small" :disabled="busy" @click="rename(list)">
                  Rename
                </button>
                <button
                  v-if="lists.groups.length"
                  type="button"
                  class="secondary small"
                  :aria-expanded="sharing === list.id"
                  @click="sharing = sharing === list.id ? null : list.id"
                >
                  Share
                </button>
                <button type="button" class="secondary small" :disabled="busy" @click="drop(list)">
                  Remove
                </button>
              </span>
            </div>
            <p v-if="list.items.some(counts)" class="larder-search-list">
              <a :href="`/search?el=${list.id}`">Search with this list</a>
            </p>
            <p v-if="!list.mine" class="muted larder-shared">
              {{ list.owner_name ?? "Someone" }}'s, shared with you through
              {{ list.shared_with.map((g) => g.name).join(", ") }}{{
                list.editable ? "" : ": you can see it, not change it"
              }}.
            </p>
            <p v-else-if="list.shared_with.length && sharing !== list.id" class="muted larder-shared">
              Shared with {{ list.shared_with.map((g) => g.name).join(", ") }}.
            </p>
            <fieldset v-if="list.mine && sharing === list.id" class="larder-share">
              <legend>Who else sees it</legend>
              <label v-for="g in lists.groups" :key="g.id" class="check">
                <input
                  type="checkbox"
                  :checked="list.shared_with.some((s) => s.id === g.id)"
                  :disabled="busy"
                  @change="toggleGroup(list, g.id, ($event.target as HTMLInputElement).checked)"
                />
                {{ g.name }}
              </label>
              <p class="help">
                Its members see it; editors and admins of the group change what's on it.
              </p>
            </fieldset>
            <form v-if="list.editable" class="inline-form" @submit.prevent="add(list)">
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
                  <label v-if="counts(item)" class="larder-tick">
                    <input
                      type="checkbox"
                      :checked="ticked.includes(item.id)"
                      @change="tick(item, ($event.target as HTMLInputElement).checked)"
                    />
                    <span class="visually-hidden">Search with {{ item.name }}</span>
                  </label>
                  <strong>{{ item.name }}</strong>
                  <span v-if="item.equipment" class="muted">
                    ·
                    <a :href="`/equipment/${item.equipment_id}`">{{ item.equipment }}</a>
                    <button
                      v-if="list.editable"
                      type="button"
                      class="secondary small"
                      :disabled="busy"
                      @click="unmatch(item)"
                    >
                      Not this
                    </button>
                  </span>
                  <span v-else class="muted">
                    · not matched, so search can't use it
                    <button
                      v-if="list.editable"
                      type="button"
                      class="secondary small"
                      :disabled="busy"
                      @click="choosing = item.id"
                    >
                      Choose what it is
                    </button>
                  </span>
                </div>
                <EquipmentPicker
                  v-if="choosing === item.id"
                  :input-id="`pick-${item.id}`"
                  :label="`What “${item.name}” is`"
                  placeholder="Find the equipment"
                  :exclude="[]"
                  @pick="(p) => choose(item, p)"
                />
                <p v-if="!list.editable" class="muted larder-state">
                  {{ STATES.find((s) => s.state === item.state)?.label }}
                </p>
                <div v-else class="larder-item-actions">
                  <div class="kind-filter" role="group" :aria-label="`${item.name}: have or want`">
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
                  <label v-if="movable.length > 1" class="larder-move">
                    <span class="visually-hidden">Move {{ item.name }} to</span>
                    <select
                      :value="item.list_id"
                      :disabled="busy"
                      @change="move(item, ($event.target as HTMLSelectElement).value)"
                    >
                      <option v-for="l in movable" :key="l.id" :value="l.id">
                        {{ l.name }}
                      </option>
                    </select>
                  </label>
                  <button
                    type="button"
                    class="secondary small"
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
            placeholder="A new list: Kitchen, Cabin, Camping box…"
          />
          <button type="submit" class="primary" :disabled="busy">Add the list</button>
        </form>
      </template>
    </template>
  </article>
</template>
