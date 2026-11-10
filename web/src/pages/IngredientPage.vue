<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import IngredientPicker from "../components/IngredientPicker.vue";
import HistoryPanel from "../components/HistoryPanel.vue";
import SwapForm from "../components/SwapForm.vue";
import SwapList from "../components/SwapList.vue";
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
  whereItIs,
} from "../ingredients";
import type { Me } from "../me";

const props = defineProps<{ id: string; user: Me | null | undefined }>();
const addingSwap = ref(false);
const ingredient = ref<Ingredient | null>(null);
const missing = ref(false);
const failed = ref(false);
const loading = ref(false);
// Ray's wireframe: the recipes counting what's under it, unless only this
// exact ingredient is asked for.
const exact = ref(false);
const hasChildren = computed(() => !!ingredient.value?.children.length);

async function load(more = false) {
  loading.value = true;
  try {
    const offset = more ? (ingredient.value?.recipes.length ?? 0) : 0;
    const page = await fetchIngredient(props.id, offset, !exact.value);
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

// Where a listed recipe is in its source, without the authors the table's
// Source column doesn't need.
function where(r: Ingredient["recipes"][number]) {
  return whereItIs({ ...r, authors: [] }) || "—";
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
  <article class="wide ingredient-page">
    <p v-if="missing">There's no ingredient here. It may have been merged into another.</p>
    <p v-else-if="failed" role="alert">This ingredient couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!ingredient" class="status">Loading…</p>
    <template v-else>
      <Teleport v-if="user?.may_edit" to="#admin-bar" defer>
        <div class="admin-bar">
          <div class="bar">
            <strong>Admin</strong>
            <a href="#ingredient-name">Rename</a>
            <a href="#merge-into">Merge into…</a>
            <a href="#parent-of">Put under…</a>
            <a href="#child-of">Add under this…</a>
            <a v-if="ingredient.aliases.length" href="#also-called">Edit other names</a>
            <a v-if="ingredient.total === 0" href="#delete-ingredient">Delete</a>
            <span v-else class="muted">Delete (only when nothing uses it)</span>
          </div>
        </div>
      </Teleport>

      <nav class="crumbs" aria-label="Breadcrumb">
        <a href="/ingredients">Ingredients</a>
        <span aria-hidden="true">/</span>
        <span aria-current="page">{{ ingredient.name }}</span>
      </nav>

      <div class="ingredient-head">
        <div>
          <h1>{{ ingredient.name }}</h1>
          <p class="status">
            Used in {{ ingredient.family_total.toLocaleString() }}
            {{ ingredient.family_total === 1 ? "recipe" : "recipes"
            }}{{ hasChildren ? ", counting what's under it" : "" }}
          </p>
        </div>
        <a :href="`/search?i=${ingredient.id}`" class="button-primary"
          >Search with {{ ingredient.name.toLowerCase() }}</a
        >
      </div>

      <div class="ingredient-cards">
        <div>
          <h2>Comes under</h2>
          <p v-if="ingredient.parent">
            <a :href="`/ingredients/${ingredient.parent.id}`">{{ ingredient.parent.name }}</a>
          </p>
          <p v-else class="status">Nothing broader yet.</p>
        </div>
        <div>
          <h2>Includes</h2>
          <p v-if="ingredient.children.length">
            <template v-for="(c, i) in ingredient.children" :key="c.id"
              ><template v-if="i > 0"> · </template
              ><a :href="`/ingredients/${c.id}`">{{ c.name }}</a></template
            >
          </p>
          <p v-else class="status">Nothing narrower yet.</p>
        </div>
        <div id="also-called">
          <h2>Also called</h2>
          <p v-if="ingredient.aliases.length">
            <template v-for="(a, i) in ingredient.aliases" :key="a.id">
              <template v-if="i > 0"> · </template>
              <span>{{ a.name }}</span>
              <button
                v-if="user?.may_edit"
                type="button"
                class="link remove-alias"
                :aria-label="`Stop matching ${a.name}`"
                @click="removeAlias(a)"
              >
                ×
              </button>
            </template>
          </p>
          <p v-else class="status">No other names yet.</p>
        </div>
      </div>

      <section class="source-section">
        <div class="table-head">
          <h2>Recipes using {{ ingredient.name.toLowerCase() }}</h2>
          <label v-if="hasChildren" class="check"
            ><input v-model="exact" type="checkbox" @change="load()" /> Only this exact
            ingredient</label
          >
        </div>
        <table v-if="ingredient.recipes.length" class="recipe-table">
          <thead>
            <tr>
              <th scope="col">Recipe</th>
              <th scope="col">Source</th>
              <th scope="col">Where</th>
              <th scope="col">Line as written</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in ingredient.recipes" :key="r.id">
              <td><a :href="`/recipes/${r.id}`" class="strong">{{ r.title }}</a></td>
              <td><a :href="`/sources/${r.source_id}`">{{ r.source_title }}</a></td>
              <td class="muted">{{ where(r) }}</td>
              <td class="lines">{{ r.line }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="status">No recipe uses it yet.</p>
        <button
          v-if="ingredient.recipes.length < ingredient.listed_total"
          type="button"
          class="secondary show-more"
          :disabled="loading"
          @click="load(true)"
        >
          Show more ({{ (ingredient.listed_total - ingredient.recipes.length).toLocaleString() }}
          left)
        </button>
      </section>

      <section v-if="ingredient.swaps.length || user?.may_edit" class="source-section">
        <div class="table-head">
          <h2>Swaps</h2>
          <button
            v-if="user?.may_edit && !addingSwap"
            type="button"
            class="link"
            @click="addingSwap = true"
          >
            + Add a swap
          </button>
        </div>
        <SwapList
          v-if="ingredient.swaps.length"
          :swaps="ingredient.swaps"
          :can-edit="!!user?.may_edit"
          @removed="(id) => (ingredient!.swaps = ingredient!.swaps.filter((s) => s.id !== id))"
        />
        <p v-else class="status">None recorded yet.</p>
        <SwapForm
          v-if="user?.may_edit && addingSwap"
          :choices="[{ kind: 'ingredient', id: ingredient.id, name: ingredient.name }]"
          @added="(s) => ingredient!.swaps.push(s)"
        />
      </section>

      <section v-if="user?.may_edit" class="fix-ingredient source-section">
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
          <button id="delete-ingredient" type="button" class="link" @click="remove">
            Delete this ingredient
          </button>
        </p>
      </section>
      <HistoryPanel kind="ingredients" :id="id" :can-revert="!!user?.may_edit" />
    </template>
  </article>
</template>
