<script setup lang="ts">
import { onMounted, ref } from "vue";
import IngredientPicker from "../components/IngredientPicker.vue";
import {
  deleteAlias,
  deleteIngredient,
  fetchIngredient,
  type Ingredient,
  mergeIngredient,
  type Named,
  renameIngredient,
  setParent,
  Taken,
} from "../ingredients";
import type { Me } from "../me";

const props = defineProps<{ id: string; user: Me | null | undefined }>();
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
      newName.value = page.name;
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

// Fixing it, for admins.

const newName = ref("");
const error = ref("");
// Set when the new name is another ingredient's, to offer merging into it.
const taken = ref<Named | null>(null);
const busy = ref(false);

async function rename() {
  if (!ingredient.value || !newName.value.trim()) return;
  error.value = "";
  taken.value = null;
  busy.value = true;
  try {
    const renamed = await renameIngredient(ingredient.value.id, newName.value);
    await load();
    newName.value = renamed.name;
  } catch (e) {
    if (e instanceof Taken) taken.value = e.ingredient;
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

// Puts one ingredient under another (or under nothing), then shows the
// change here.
async function placeUnder(child: string, parent: string | null) {
  error.value = "";
  busy.value = true;
  try {
    await setParent(child, parent);
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function merge(into: Named) {
  const here = ingredient.value;
  if (!here) return;
  const n = here.total;
  const uses = n === 1 ? "The recipe that uses it" : `The ${n.toLocaleString()} recipes that use it`;
  const message =
    `Merge “${here.name}” into “${into.name}”?\n\n` +
    `${n ? `${uses} will use “${into.name}”, and ` : ""}` +
    `“${here.name}” will be another name for it.`;
  if (!confirm(message)) return;
  error.value = "";
  busy.value = true;
  try {
    const left = await mergeIngredient(here.id, into.id);
    location.href = `/ingredients/${left.id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    busy.value = false;
  }
}

async function remove() {
  const here = ingredient.value;
  if (!here || !confirm(`Delete “${here.name}”? No recipe uses it.`)) return;
  error.value = "";
  try {
    await deleteIngredient(here.id);
    location.href = "/ingredients";
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function removeAlias(alias: Ingredient["aliases"][number]) {
  const here = ingredient.value;
  const message =
    `Stop matching “${alias.name}” to “${here?.name}”?\n\n` +
    "Recipes already matched keep it. Lines written that way from now on " +
    "become an ingredient of their own.";
  if (!here || !confirm(message)) return;
  error.value = "";
  try {
    await deleteAlias(here.id, alias.id);
    here.aliases = here.aliases.filter((a) => a.id !== alias.id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
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
      <p v-if="ingredient.parent" class="byline">
        A kind of
        <a :href="`/ingredients/${ingredient.parent.id}`">{{ ingredient.parent.name }}</a>
      </p>
      <h1>{{ ingredient.name }}</h1>
      <p v-if="ingredient.children.length">
        Includes
        <template v-for="(c, i) in ingredient.children" :key="c.id">
          <template v-if="i > 0">, </template>
          <a :href="`/ingredients/${c.id}`">{{ c.name }}</a>
        </template>
      </p>
      <p v-if="ingredient.aliases.length" class="aliases">
        Also written as
        <template v-for="(a, i) in ingredient.aliases" :key="a.id">
          <template v-if="i > 0">, </template>
          <span>{{ a.name }}</span>
          <button
            v-if="user?.is_admin"
            type="button"
            class="link remove-alias"
            :aria-label="`Stop matching ${a.name}`"
            @click="removeAlias(a)"
          >
            ×
          </button>
        </template>
      </p>
      <p class="status">
        Used in {{ ingredient.total.toLocaleString() }}
        {{ ingredient.total === 1 ? "recipe" : "recipes" }}<template
          v-if="ingredient.family_total > ingredient.total"
          >, or
          <a :href="`/search?i=${ingredient.id}`"
            >{{ ingredient.family_total.toLocaleString() }} with those under it</a
          ></template
        >.
        <a :href="`/search?i=${ingredient.id}`">Search with other ingredients too</a>
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

      <section v-if="user?.is_admin" class="fix-ingredient">
        <h2>Fix this ingredient</h2>
        <p class="status">
          A recipe matched to the wrong ingredient is fixed on the recipe, by correcting its line.
        </p>
        <p v-if="error" class="error" role="alert">
          {{ error }}
          <template v-if="taken">
            <button type="button" class="link" :disabled="busy" @click="merge(taken)">
              Merge into “{{ taken.name }}”
            </button>
          </template>
        </p>

        <form class="isbn-form" @submit.prevent="rename">
          <label for="ingredient-name">Name</label>
          <div class="row">
            <input id="ingredient-name" v-model="newName" required autocomplete="off" />
            <button
              type="submit"
              class="primary"
              :disabled="busy || newName.trim() === ingredient.name"
            >
              Rename
            </button>
          </div>
        </form>

        <IngredientPicker
          input-id="merge-into"
          label="Merge into another ingredient"
          placeholder="the one to keep"
          :exclude="[ingredient.id]"
          :disabled="busy"
          @pick="merge"
        />

        <h3>Broader and narrower</h3>
        <p class="status">
          A search for an ingredient also finds the ones under it: put Fresh Ginger and Ground
          Ginger under Ginger.
        </p>
        <p v-if="ingredient.parent">
          Under “{{ ingredient.parent.name }}”.
          <button
            type="button"
            class="link"
            :disabled="busy"
            @click="placeUnder(ingredient.id, null)"
          >
            Take it out from under
          </button>
        </p>
        <IngredientPicker
          input-id="parent-of"
          :label="ingredient.parent ? 'Move it under another ingredient' : 'Put it under'"
          placeholder="ginger"
          :exclude="[ingredient.id, ingredient.parent?.id ?? '']"
          :disabled="busy"
          @pick="(p) => placeUnder(ingredient!.id, p.id)"
        />
        <IngredientPicker
          input-id="child-of"
          label="Put another ingredient under this one"
          placeholder="fresh ginger"
          :exclude="[ingredient.id, ...ingredient.children.map((c) => c.id)]"
          :disabled="busy"
          @pick="(c) => placeUnder(c.id, ingredient!.id)"
        />
        <p v-if="ingredient.children.length" class="status">
          Under it now:
          <template v-for="(c, i) in ingredient.children" :key="c.id">
            <template v-if="i > 0">, </template>
            {{ c.name }}
            <button
              type="button"
              class="link remove-alias"
              :disabled="busy"
              :aria-label="`Take ${c.name} out from under it`"
              @click="placeUnder(c.id, null)"
            >
              ×
            </button>
          </template>
        </p>

        <p v-if="ingredient.total === 0">
          <button type="button" class="link" @click="remove">Delete this ingredient</button>
        </p>
      </section>
    </template>
  </article>
</template>
