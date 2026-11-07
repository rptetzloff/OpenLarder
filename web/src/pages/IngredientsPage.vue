<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { type IngredientSummary, listIngredients } from "../ingredients";

document.title = "Ingredients · OpenLarder";

const q = ref(new URLSearchParams(location.search).get("q") ?? "");
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
    const page = await listIngredients(q.value, more ? (ingredients.value?.length ?? 0) : 0);
    if (mine !== asked) return;
    ingredients.value = more ? [...(ingredients.value ?? []), ...page.ingredients] : page.ingredients;
    total.value = page.total;
  } catch {
    if (mine === asked) failed.value = true;
  } finally {
    if (mine === asked) loading.value = false;
  }
}

let timer: ReturnType<typeof setTimeout> | undefined;
watch(q, () => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    const url = new URL(location.href);
    if (q.value.trim()) url.searchParams.set("q", q.value.trim());
    else url.searchParams.delete("q");
    history.replaceState(null, "", url);
    load();
  }, 200);
});
onMounted(() => load());
</script>

<template>
  <article>
    <h1>Ingredients</h1>
    <p class="status">
      Every ingredient the indexed recipes use, most used first. Open one to see the recipes that
      use it.
    </p>
    <div class="isbn-form">
      <label for="ingredient-filter">Find an ingredient</label>
      <div class="row">
        <input
          id="ingredient-filter"
          v-model="q"
          type="search"
          autocomplete="off"
          placeholder="rhubarb"
        />
      </div>
    </div>
    <p v-if="failed" role="alert">The ingredients couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="ingredients === null" class="status">Loading…</p>
    <p v-else-if="ingredients.length === 0" class="status">
      {{ q.trim() ? `No ingredient matches “${q.trim()}”.` : "No ingredients yet." }}
    </p>
    <template v-else>
      <p class="status">
        {{ total.toLocaleString() }} {{ total === 1 ? "ingredient" : "ingredients" }}
      </p>
      <ul class="recipe-list">
        <li v-for="i in ingredients" :key="i.id">
          <a :href="`/ingredients/${i.id}`">{{ i.name }}</a>
          <span class="page-ref">
            {{ i.recipes.toLocaleString() }} {{ i.recipes === 1 ? "recipe" : "recipes" }}
          </span>
        </li>
      </ul>
      <button
        v-if="ingredients.length < total"
        type="button"
        class="primary"
        :disabled="loading"
        @click="load(true)"
      >
        Show more ({{ (total - ingredients.length).toLocaleString() }} left)
      </button>
    </template>
  </article>
</template>
