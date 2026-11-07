<script setup lang="ts">
import { onMounted, ref } from "vue";
import { fetchIngredient, type Ingredient } from "../ingredients";

const props = defineProps<{ id: string }>();
const ingredient = ref<Ingredient | null>(null);
const missing = ref(false);
const failed = ref(false);
const loading = ref(false);

async function load(more = false) {
  loading.value = true;
  try {
    const offset = more ? (ingredient.value?.recipes.length ?? 0) : 0;
    const page = await fetchIngredient(props.id, offset);
    if (page === null) missing.value = true;
    else if (more && ingredient.value) ingredient.value.recipes.push(...page.recipes);
    else {
      ingredient.value = page;
      document.title = `${page.name} · Ingredients · OpenLarder`;
    }
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

function where(r: Ingredient["recipes"][number]) {
  return r.pages.length ? `, p. ${r.pages.join(" / ")}` : "";
}

onMounted(() => load());
</script>

<template>
  <article>
    <p><a href="/ingredients">← All ingredients</a></p>
    <p v-if="missing">There's no ingredient here. It may have been merged into another.</p>
    <p v-else-if="failed" role="alert">This ingredient couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!ingredient" class="status">Loading…</p>
    <template v-else>
      <h1>{{ ingredient.name }}</h1>
      <p class="status">
        Used in {{ ingredient.total.toLocaleString() }}
        {{ ingredient.total === 1 ? "recipe" : "recipes" }}.
      </p>
      <ul class="recipe-list">
        <li v-for="r in ingredient.recipes" :key="r.id">
          <a :href="`/recipes/${r.id}`">{{ r.title }}</a>
          <span class="page-ref">
            <a :href="`/books/${r.book_id}`">{{ r.book_title }}</a>{{ where(r) }}
          </span>
        </li>
      </ul>
      <button
        v-if="ingredient.recipes.length < ingredient.total"
        type="button"
        class="primary"
        :disabled="loading"
        @click="load(true)"
      >
        Show more ({{ (ingredient.total - ingredient.recipes.length).toLocaleString() }} left)
      </button>
    </template>
  </article>
</template>
