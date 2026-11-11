<script setup lang="ts">
import { computed, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import { DATA_TYPES, type Food } from "../ingredients";
import type { Me } from "../me";

// Suggested links from ingredients to USDA FoodData Central and Wikidata
// (fdc_match.py), most used first, for a moderator to accept or dismiss.
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Ingredient links · Admin · OpenLarder";

type Show = "likely" | "unsure" | "wikidata";
interface Row {
  ingredient: { id: string; name: string; recipes: number };
  fdc: { id: string; certainty: "likely" | "unsure"; food: Food } | null;
  wikidata: {
    id: string;
    certainty: "likely" | "unsure";
    wikidata_id: string;
    label: string | null;
    url: string;
  } | null;
}

const TABS: [Show, string][] = [
  ["likely", "Likely foods"],
  ["unsure", "Unsure foods"],
  ["wikidata", "Wikidata items"],
];
const show = ref<Show>("likely");
const rows = ref<Row[] | null>(null);
const counts = ref<Record<Show, number>>({ likely: 0, unsure: 0, wikidata: 0 });
const total = ref(0);
const error = ref("");
const busy = ref(false);
const note = ref("");
const suggesting = ref(false);

async function load() {
  error.value = "";
  try {
    const res = await fetch(`/api/fdc/suggestions?show=${show.value}`);
    if (!res.ok) throw new Error("The suggestions couldn't be loaded. Try reloading the page.");
    const page = await res.json();
    rows.value = page.rows;
    counts.value = page.counts;
    total.value = page.total;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function post(path: string, body?: unknown) {
  const res = await fetch(path, {
    method: "POST",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const out = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof out.detail === "string" ? out.detail : "That didn't work.");
  return out;
}

async function decide(action: "accept" | "dismiss", ids: string[]) {
  if (!ids.length) return;
  busy.value = true;
  error.value = "";
  note.value = "";
  try {
    const out = await post(`/api/fdc/suggestions/${action}`, { ids });
    if (ids.length > 1)
      note.value = `${action === "accept" ? "Linked" : "Dismissed"} ${out.done.toLocaleString()}.`;
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

// The column this tab is about.
const ofTab = (r: Row) => (show.value === "wikidata" ? r.wikidata : r.fdc);
const pageIds = computed(() => (rows.value ?? []).map(ofTab).filter((s) => s).map((s) => s!.id));

async function suggest() {
  suggesting.value = true;
  error.value = "";
  note.value = "";
  try {
    const out = await post("/api/fdc/suggest");
    note.value = `${out.fdc.toLocaleString()} new foods and ${out.wikidata.toLocaleString()} new Wikidata items suggested.`;
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    suggesting.value = false;
  }
}

watch(
  () => !!props.user?.may_edit,
  (yes) => yes && rows.value === null && load(),
  { immediate: true },
);
watch(show, () => {
  rows.value = null;
  note.value = "";
  load();
});
</script>

<template>
  <AdminBar v-if="user?.may_edit" :user="user" current="/admin/links" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/admin">Admin</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">Ingredient links</span>
    </nav>
    <div class="list-head">
      <h1>Ingredient links</h1>
      <p class="muted">
        The USDA FoodData Central food and the Wikidata item each ingredient is probably the same
        as, the most used first. Likely: the food's words are the ingredient's. Unsure: one word
        more, which is often a different food. Wikidata items come through USDA's numbers, and are
        often the plant rather than the food: check each. Nothing is linked until it's accepted, and
        a dismissed one isn't suggested again.
      </p>
    </div>
    <p v-if="!user?.may_edit" class="status">This is for moderators.</p>
    <template v-else>
      <div class="links-tools">
        <div class="filter-buttons" role="group" aria-label="Show">
          <button
            v-for="[key, label] in TABS"
            :key="key"
            type="button"
            class="secondary"
            :aria-pressed="show === key"
            @click="show = key"
          >
            {{ label }} <span class="count">{{ counts[key].toLocaleString() }}</span>
          </button>
        </div>
        <button
          v-if="user.may_run"
          type="button"
          class="secondary"
          :disabled="suggesting"
          @click="suggest"
        >
          {{ suggesting ? "Suggesting…" : "Suggest links" }}
        </button>
      </div>
      <p v-if="note" class="status" aria-live="polite">{{ note }}</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="rows === null && !error" class="status">Loading…</p>
      <p v-else-if="rows && !rows.length" class="status">
        Nothing to decide here.<template v-if="user.may_run">
          “Suggest links” looks for more, once FoodData Central is loaded (Admin).</template
        >
      </p>
      <template v-else-if="rows">
        <div v-if="show === 'likely'" class="bulk">
          <button type="button" class="primary" :disabled="busy" @click="decide('accept', pageIds)">
            Accept all {{ pageIds.length.toLocaleString() }} shown
          </button>
          <span class="muted"
            >{{ total.toLocaleString() }} in all; a hundred at a time, the most used first.</span
          >
        </div>
        <table class="recipe-table links-table">
          <thead>
            <tr>
              <th scope="col">Ingredient</th>
              <th scope="col">{{ show === "wikidata" ? "Wikidata item" : "FoodData Central food" }}</th>
              <th scope="col"><span class="visually-hidden">Decide</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.ingredient.id">
              <td>
                <a :href="`/ingredients/${r.ingredient.id}`" class="strong">{{ r.ingredient.name }}</a>
                <div class="muted">
                  {{ r.ingredient.recipes.toLocaleString() }}
                  {{ r.ingredient.recipes === 1 ? "recipe" : "recipes" }}
                </div>
              </td>
              <td v-if="show !== 'wikidata' && r.fdc">
                <a :href="r.fdc.food.url" rel="noopener">{{ r.fdc.food.description }}</a>
                <div class="muted">
                  {{ DATA_TYPES[r.fdc.food.data_type]
                  }}<template v-if="r.fdc.food.category"> · {{ r.fdc.food.category }}</template>
                </div>
              </td>
              <td v-else-if="r.wikidata">
                <a :href="r.wikidata.url" rel="noopener">{{ r.wikidata.label ?? r.wikidata.wikidata_id }}</a>
                <div class="muted">{{ r.wikidata.wikidata_id }}</div>
              </td>
              <td v-else></td>
              <td class="decide">
                <button
                  type="button"
                  class="secondary"
                  :disabled="busy"
                  :aria-label="`Accept for ${r.ingredient.name}`"
                  @click="decide('accept', [ofTab(r)!.id])"
                >
                  Accept
                </button>
                <button
                  type="button"
                  class="link"
                  :disabled="busy"
                  :aria-label="`Dismiss for ${r.ingredient.name}`"
                  @click="decide('dismiss', [ofTab(r)!.id])"
                >
                  Dismiss
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </template>
  </article>
</template>

<style scoped>
.links-tools {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}
.filter-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.filter-buttons button[aria-pressed="true"] {
  font-weight: 600;
  outline: 2px solid currentColor;
  outline-offset: 1px;
}
.bulk {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  margin: 0.5rem 0 1rem;
}
.links-table td {
  overflow-wrap: anywhere;
}
.decide {
  white-space: nowrap;
}
.decide button + button {
  margin-left: 0.5rem;
}
</style>
