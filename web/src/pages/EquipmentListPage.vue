<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { type EquipmentSummary, listEquipment } from "../equipment";

document.title = "Equipment · OpenLarder";

const params = new URLSearchParams(location.search);
const q = ref(params.get("q") ?? "");
// Most needed first, or A to Z.
const sort = ref<"uses" | "name">(params.get("sort") === "name" ? "name" : "uses");
// What any kitchen has is left out until asked for: no recipe lists it.
const assumed = ref(params.get("assumed") === "true");
const equipment = ref<EquipmentSummary[] | null>(null);
const total = ref(0);
const failed = ref(false);
const loading = ref(false);
// Answers can arrive out of order as someone types; only the latest counts.
let asked = 0;

// A name typed is looked for among everything: someone looking for
// "skillet" finds it, and why no recipe lists one (Ray's spec, 2026-11-15).
const everything = computed(() => assumed.value || !!q.value.trim());
// How many recipes need each thing is a column, and an order to choose,
// once any recipe is recorded as needing any of them. Until a recipe's
// needs can be recorded (the recipe form's field comes next) every count
// is nought, and a hundred noughts say nothing.
const counted = ref(false);

async function load(more = false) {
  const mine = ++asked;
  loading.value = true;
  failed.value = false;
  try {
    const page = await listEquipment(q.value, more ? (equipment.value?.length ?? 0) : 0, {
      sort: sort.value,
      assumed: everything.value,
    });
    if (mine !== asked) return;
    equipment.value = more ? [...(equipment.value ?? []), ...page.equipment] : page.equipment;
    total.value = page.total;
    if (page.equipment.some((e) => e.recipes > 0)) counted.value = true;
  } catch {
    if (mine === asked) failed.value = true;
  } finally {
    if (mine === asked) loading.value = false;
  }
}

// The address keeps what's chosen, so a list can be shared.
function remember() {
  const url = new URL(location.href);
  for (const key of ["q", "sort", "assumed"]) url.searchParams.delete(key);
  if (q.value.trim()) url.searchParams.set("q", q.value.trim());
  if (sort.value === "name") url.searchParams.set("sort", "name");
  if (assumed.value) url.searchParams.set("assumed", "true");
  history.replaceState(null, "", url);
}

let timer: ReturnType<typeof setTimeout> | undefined;
watch(q, () => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    remember();
    load();
  }, 200);
});
watch([sort, assumed], () => {
  remember();
  load();
});
onMounted(() => load());
</script>

<template>
  <article class="wide equipment-list-page">
    <div class="list-head">
      <h1>Equipment</h1>
      <p class="muted">
        What some recipes can't be made without, from a stand mixer to a springform pan. A knife
        or a mixing bowl isn't listed on a recipe: any kitchen has one.
      </p>
    </div>

    <div class="list-tools">
      <div class="list-find">
        <label for="equipment-filter">Find equipment</label>
        <input
          id="equipment-filter"
          v-model="q"
          type="search"
          autocomplete="off"
          placeholder="Name, or another name for it"
        />
      </div>
      <div class="table-controls">
        <label class="check"><input v-model="assumed" type="checkbox" /> Show what's assumed</label>
        <template v-if="counted">
          <label for="equipment-sort">Sort</label>
          <select id="equipment-sort" v-model="sort">
            <option value="uses">Most needed</option>
            <option value="name">A to Z</option>
          </select>
        </template>
      </div>
    </div>

    <p v-if="failed" role="alert">The equipment couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="equipment === null" class="status">Loading…</p>
    <p v-else-if="equipment.length === 0" class="status">
      {{ q.trim() ? `No equipment matches “${q.trim()}”.` : "No equipment yet." }}
    </p>
    <template v-else>
      <p class="status results-count" role="status">
        <!-- One piece of text, as the Ingredients list's count is, so no
             space is lost between its parts. -->
        {{ total.toLocaleString() }} {{ total === 1 ? "piece" : "pieces" }} of equipment{{
          q.trim() ? ` ${total === 1 ? "matches" : "match"} “${q.trim()}”` : ""
        }}.
      </p>
      <table class="recipe-table equipment-list">
        <thead>
          <tr>
            <th scope="col">Equipment</th>
            <th v-if="counted" scope="col" class="numeric">Recipes</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in equipment" :key="e.id">
            <td>
              <a :href="`/equipment/${e.id}`" class="strong">{{ e.name }}</a>
              <!-- One line, only when there's something to say, in its own
                   words: it reads without a column's heading. -->
              <span v-if="e.assumed || e.counts_as.length || e.aliases.length" class="more muted">
                <template v-if="e.assumed">Expected in any kitchen</template
                ><template v-if="e.assumed && (e.counts_as.length || e.aliases.length)"> · </template
                ><template v-if="e.counts_as.length"
                  >Counts as
                  <template v-for="(c, i) in e.counts_as" :key="c.id"
                    ><template v-if="i > 0">{{
                      i === e.counts_as.length - 1 ? " and " : ", "
                    }}</template
                    ><a :href="`/equipment/${c.id}`">{{ c.name }}</a></template
                  ></template
                ><template v-if="e.counts_as.length && e.aliases.length"> · </template
                ><template v-if="e.aliases.length">Also called {{ e.aliases.join(", ") }}</template>
              </span>
            </td>
            <!-- What any kitchen has is on no recipe: no count, not a nought. -->
            <td v-if="counted" class="numeric" :class="{ empty: e.assumed }">
              <template v-if="!e.assumed"
                >{{ e.recipes.toLocaleString() }}<span class="cell-label">
                  {{ e.recipes === 1 ? " recipe" : " recipes" }}</span
                ></template
              >
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="equipment.length < total" class="show-more">
        <button type="button" class="secondary" :disabled="loading" @click="load(true)">
          Show more ({{ (total - equipment.length).toLocaleString() }} left)
        </button>
      </p>
    </template>
  </article>
</template>

<style scoped>
/* As the Ingredients list: the name, with a line beneath when there's
   something to say of it, and how many recipes. */
.equipment-list td:first-child {
  white-space: normal;
}
.more {
  display: block;
  font-size: var(--text-sm);
}
.numeric {
  width: 6rem;
  text-align: right;
  white-space: nowrap;
}
@media (max-width: 40rem) {
  .numeric {
    width: auto;
    text-align: left;
  }
  /* A cell with nothing in it takes no row of the card. */
  td.empty {
    display: none;
  }
}
</style>
