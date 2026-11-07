<script setup lang="ts">
import { onMounted, ref } from "vue";
import FlagItem from "../components/FlagItem.vue";
import { type Flag, recipeFlags } from "../flags";
import type { Me } from "../me";
import { type Recipe, removeRecipe } from "../recipes";

const props = defineProps<{ id: string; user: Me | null | undefined }>();
const recipe = ref<Recipe | null>(null);
const missing = ref(false);
const failed = ref(false);
const error = ref("");
// Only whoever may deal with them gets any back: an admin, or who added it.
const flags = ref<Flag[]>([]);

onMounted(async () => {
  try {
    const res = await fetch(`/api/recipes/${props.id}`);
    if (res.status === 404 || res.status === 422) missing.value = true;
    else if (!res.ok) failed.value = true;
    else {
      recipe.value = await res.json();
      if (props.user !== null) flags.value = await recipeFlags(props.id);
      document.title = `${recipe.value!.title} · ${recipe.value!.book.title} · OpenLarder`;
    }
  } catch {
    failed.value = true;
  }
});

function where(p: Recipe["pages"][number]) {
  const edition = [p.edition_title, p.published_year].filter(Boolean).join(", ");
  const page = p.page ? `page ${p.page}` : "page not recorded yet";
  return edition ? `${page} (${edition})` : page;
}

async function remove() {
  if (!recipe.value || !confirm(`Remove “${recipe.value.title}” from the index?`)) return;
  try {
    await removeRecipe(recipe.value.id);
    location.href = `/books/${recipe.value.book.id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}
</script>

<template>
  <article>
    <p v-if="missing">There's no recipe here. It may have been removed, or the link is wrong.</p>
    <p v-else-if="failed" role="alert">This recipe couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!recipe" class="status">Loading…</p>
    <template v-else>
      <p><a :href="`/books/${recipe.book.id}`">← {{ recipe.book.title }}</a></p>
      <h1>{{ recipe.title }}</h1>
      <p class="byline">
        In <a :href="`/books/${recipe.book.id}`">{{ recipe.book.title }}</a>,
        {{ recipe.pages.map(where).join("; ") }}
      </p>

      <h2>Ingredients</h2>
      <ul v-if="recipe.lines.length">
        <li v-for="(line, i) in recipe.lines" :key="i">
          <template v-for="(o, j) in line.options" :key="j">
            <template v-if="j > 0">{{ j < line.options.length - 1 ? ", " : line.options.length > 2 ? ", or " : " or " }}</template>
            <a v-if="o.recipe" :href="`/recipes/${o.recipe.id}`">{{ o.name }}</a>
            <template v-else>{{ o.name }}</template>
            <span v-if="o.page" class="page-ref">p. {{ o.page }}</span>
          </template>
        </li>
      </ul>
      <p v-else class="status">No ingredients recorded yet.</p>
      <p class="status">The amounts and the method are in the book.</p>

      <template v-if="recipe.used_in.length">
        <h2>Used in</h2>
        <ul class="recipe-list">
          <li v-for="r in recipe.used_in" :key="r.id">
            <a :href="`/recipes/${r.id}`">{{ r.title }}</a>
          </li>
        </ul>
      </template>

      <section v-if="flags.some((f) => !f.resolution)" class="recipe-flags">
        <h2>Flags</h2>
        <ul class="flag-list">
          <FlagItem
            v-for="f in flags.filter((f) => !f.resolution)"
            :key="f.id"
            :flag="f"
            :show-recipe="false"
            @resolved="(u) => (flags = flags.map((x) => (x.id === u.id ? u : x)))"
          />
        </ul>
      </section>

      <div v-if="user?.is_admin" class="admin-actions">
        <a :href="`/recipes/${recipe.id}/edit`">Edit</a>
        <button type="button" class="link" @click="remove">Remove</button>
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </template>
  </article>
</template>
