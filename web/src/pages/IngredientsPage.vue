<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { type IngredientSummary, listIngredients } from "../ingredients";

document.title = "Ingredients · OpenLarder";

const params = new URLSearchParams(location.search);
const q = ref(params.get("q") ?? "");
// Most used first, or A to Z; and everything, or only what comes under
// nothing, to browse the hierarchy from the top.
const sort = ref<"uses" | "name">(params.get("sort") === "name" ? "name" : "uses");
const top = ref(params.get("top") === "true");
const ingredients = ref<IngredientSummary[] | null>(null);
const total = ref(0);
const failed = ref(false);
const loading = ref(false);
// Answers can arrive out of order as someone types; only the latest counts.
let asked = 0;

async function load(more = false) {
  const mine = ++asked;
  loading.value = true;
  failed.value = false;
  try {
    const page = await listIngredients(q.value, more ? (ingredients.value?.length ?? 0) : 0, {
      sort: sort.value,
      top: top.value,
    });
    if (mine !== asked) return;
    ingredients.value = more ? [...(ingredients.value ?? []), ...page.ingredients] : page.ingredients;
    total.value = page.total;
  } catch {
    if (mine === asked) failed.value = true;
  } finally {
    if (mine === asked) loading.value = false;
  }
}

// The address keeps what's chosen, so a list can be shared.
function remember() {
  const url = new URL(location.href);
  for (const key of ["q", "sort", "top"]) url.searchParams.delete(key);
  if (q.value.trim()) url.searchParams.set("q", q.value.trim());
  if (sort.value === "name") url.searchParams.set("sort", "name");
  if (top.value) url.searchParams.set("top", "true");
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
watch([sort, top], () => {
  remember();
  load();
});
onMounted(() => load());
</script>

<template>
  <article class="wide ingredients-page">
    <div class="list-head">
      <h1>Ingredients</h1>
      <p class="muted">
        Every ingredient the indexed recipes use. Open one to see the recipes that use it, or
        <a href="/search">search with what you have</a>.
      </p>
    </div>

    <div class="list-tools">
      <div class="list-find">
        <label for="ingredient-filter">Find an ingredient</label>
        <input
          id="ingredient-filter"
          v-model="q"
          type="search"
          autocomplete="off"
          placeholder="Name, or another name for it"
        />
      </div>
      <div class="table-controls">
        <label class="check"><input v-model="top" type="checkbox" /> Top level only</label>
        <label for="ingredient-sort">Sort</label>
        <select id="ingredient-sort" v-model="sort">
          <option value="uses">Most used</option>
          <option value="name">A to Z</option>
        </select>
      </div>
    </div>

    <p v-if="failed" role="alert">The ingredients couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="ingredients === null" class="status">Loading…</p>
    <p v-else-if="ingredients.length === 0" class="status">
      {{ q.trim() ? `No ingredient matches “${q.trim()}”.` : "No ingredients yet." }}
    </p>
    <template v-else>
      <p class="status results-count" role="status">
        {{ total.toLocaleString() }} {{ total === 1 ? "ingredient" : "ingredients"
        }}<template v-if="top"> at the top level</template><template v-if="q.trim()">
          {{ total === 1 ? "matches" : "match" }} “{{ q.trim() }}”</template
        >.
      </p>
      <table class="recipe-table ingredient-list">
        <thead>
          <tr>
            <th scope="col">Ingredient</th>
            <th scope="col">Comes under</th>
            <th scope="col">Also called</th>
            <th scope="col" class="numeric">Recipes</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="i in ingredients" :key="i.id">
            <td>
              <a :href="`/ingredients/${i.id}`" class="strong">{{ i.name }}</a>
            </td>
            <!-- On a phone the headings go, so each cell says what it is,
                 and an empty one goes too. -->
            <td :class="{ empty: !i.parent }">
              <template v-if="i.parent">
                <span class="cell-label">Under </span>
                <a :href="`/ingredients/${i.parent.id}`">{{ i.parent.name }}</a>
              </template>
              <span v-else class="muted"
                ><span aria-hidden="true">—</span><span class="visually-hidden">None</span></span
              >
            </td>
            <td :class="{ empty: !i.aliases?.length }">
              <template v-if="i.aliases?.length">
                <span class="cell-label">Also called </span>{{ i.aliases.join(" · ") }}
              </template>
              <span v-else class="muted"
                ><span aria-hidden="true">—</span><span class="visually-hidden">None</span></span
              >
            </td>
            <td class="numeric">
              {{ i.recipes.toLocaleString() }}<span class="cell-label">
                {{ i.recipes === 1 ? " recipe" : " recipes" }}</span
              >
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="ingredients.length < total" class="show-more">
        <button type="button" class="secondary" :disabled="loading" @click="load(true)">
          Show more ({{ (total - ingredients.length).toLocaleString() }} left)
        </button>
      </p>
    </template>
  </article>
</template>
