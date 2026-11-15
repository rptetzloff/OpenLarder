<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import { list as allergenList, loadAllergens } from "../allergens";
import {
  type Diet,
  createDiet,
  dietUse,
  listDiets,
  removeDiet,
  renameDiet,
  setDietAllergens,
} from "../substitutions";

// The diets, and which allergens each avoids, for "Cooking for a diet" on
// recipes (diets.py). Moderators add one here, rename it, change what it
// avoids and remove it (Ray, 2026-11-14: "ability for admin to create
// diets", and of what else to put with it, renaming and removing). What a
// diet avoids only together still has no form.
const diets = ref<Diet[]>([]);
const editing = ref<string | null>(null);
const name = ref("");
const picked = ref<string[]>([]);
const saving = ref(false);
const error = ref("");
// Why a diet can't be removed yet: the swaps recorded for it, and the
// ingredients whose pages they're on.
const held = ref<{ swaps: number; ingredients: { id: string; name: string }[] } | null>(null);
// What was last done, said to a screen reader too.
const note = ref("");

const adding = ref(false);
const newName = ref("");
const newPicked = ref<string[]>([]);
const addError = ref("");
const addButton = ref<HTMLButtonElement | null>(null);

onMounted(async () => {
  loadAllergens();
  diets.value = await listDiets().catch(() => []);
});

const labels = computed(
  () => Object.fromEntries((allergenList.value ?? []).map((a) => [a.key, a.label])) as Record<string, string>,
);

const byName = (a: Diet, b: Diet) => a.name.toLowerCase().localeCompare(b.name.toLowerCase());
const said = (e: unknown) => (e instanceof Error ? e.message : String(e));
const many = (n: number, one: string, more: string) => `${n.toLocaleString()} ${n === 1 ? one : more}`;

function start(d: Diet) {
  editing.value = d.id;
  name.value = d.name;
  picked.value = [...d.avoids];
  error.value = "";
  held.value = null;
  note.value = "";
  adding.value = false;
}

async function save(d: Diet) {
  saving.value = true;
  error.value = "";
  held.value = null;
  try {
    let updated = d;
    // Each only when it changed, so the history shows what was done.
    if (name.value.trim().replace(/\s+/g, " ") !== d.name) updated = await renameDiet(d.id, name.value);
    const same = picked.value.length === d.avoids.length && picked.value.every((k) => d.avoids.includes(k));
    if (!same) updated = await setDietAllergens(d.id, picked.value);
    diets.value = diets.value.map((x) => (x.id === d.id ? updated : x)).sort(byName);
    editing.value = null;
    note.value = updated === d ? "" : `${updated.name} is saved.`;
  } catch (e) {
    error.value = said(e);
    // A rename may have gone through before what it avoids didn't.
    diets.value = await listDiets().catch(() => diets.value);
  } finally {
    saving.value = false;
  }
}

async function remove(d: Diet) {
  saving.value = true;
  error.value = "";
  held.value = null;
  try {
    const use = await dietUse(d.id);
    if (use.swaps) {
      held.value = { swaps: use.swaps, ingredients: use.swap_ingredients };
      return;
    }
    const where =
      use.recipes || use.sources
        ? `It comes off ${many(use.recipes, "recipe", "recipes")} and ${many(use.sources, "source", "sources")} in the catalog, and off any family's own recipes that have it.`
        : "Nothing in the catalog has it; it comes off any family's own recipes that do.";
    const asked = `Remove ${d.name}? ${where} Recent changes can undo this, unless a family's recipe had it.`;
    if (!confirm(asked)) return;
    await removeDiet(d.id);
    diets.value = diets.value.filter((x) => x.id !== d.id);
    editing.value = null;
    note.value = `${d.name} is removed.`;
  } catch (e) {
    error.value = said(e);
  } finally {
    saving.value = false;
  }
}

function startAdding() {
  adding.value = true;
  editing.value = null;
  newName.value = "";
  newPicked.value = [];
  addError.value = "";
  note.value = "";
}

async function stopAdding() {
  adding.value = false;
  await nextTick();
  addButton.value?.focus();
}

async function add() {
  saving.value = true;
  addError.value = "";
  try {
    const made = await createDiet(newName.value, newPicked.value);
    diets.value = [...diets.value, made].sort(byName);
    note.value = `${made.name} is added.`;
    await stopAdding();
  } catch (e) {
    addError.value = said(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section class="tool-panel diet-avoids" aria-labelledby="diets-title">
    <h3 id="diets-title">Diets and what they avoid</h3>
    <p class="muted">
      A recipe's “Cooking for a diet” checks its ingredients for these allergens, and offers the
      swaps recorded for a diet that avoids them too. A diet avoiding none isn't offered there,
      and is still a tag for recipes and sources. What a diet avoids only together (Kosher: meat
      with milk) is set in the database, not here.
    </p>
    <ul class="diet-list">
      <li v-for="d in diets" :key="d.id">
        <template v-if="editing !== d.id">
          <strong>{{ d.name }}</strong>
          <span class="muted">
            ·
            {{ d.avoids.length ? d.avoids.map((k) => labels[k] ?? k).join(", ") : "nothing"
            }}<template v-if="d.together.length"
              >; and, only together,
              {{
                d.together
                  .map((p) => `${labels[p.allergen] ?? p.allergen} with ${(labels[p.other] ?? p.other).toLowerCase()}`)
                  .join(", ")
              }}</template
            ></span
          >
          <button
            type="button"
            class="secondary small change"
            :aria-label="`Change ${d.name}`"
            @click="start(d)"
          >
            Change
          </button>
        </template>
        <form v-else @submit.prevent="save(d)">
          <label :for="`diet-name-${d.id}`">Name</label>
          <input :id="`diet-name-${d.id}`" v-model="name" maxlength="60" required />
          <fieldset>
            <legend>Avoids</legend>
            <label v-for="a in allergenList ?? []" :key="a.key" class="check">
              <input v-model="picked" type="checkbox" :value="a.key" /> {{ a.label }}
            </label>
          </fieldset>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <p v-if="held" class="error" role="alert">
            {{ many(held.swaps, "swap is", "swaps are") }} recorded for {{ d.name }}, and
            {{ held.swaps === 1 ? "holds" : "hold" }} it here. Remove
            {{ held.swaps === 1 ? "it" : "them" }} first<template v-if="held.ingredients.length"
              >, on the page of
              <template v-for="(i, n) in held.ingredients" :key="i.id"
                ><template v-if="n">, </template><a :href="`/ingredients/${i.id}`">{{ i.name }}</a></template
              ></template
            >.
          </p>
          <div class="actions">
            <button type="submit" class="primary small" :disabled="saving">
              {{ saving ? "Saving…" : "Save" }}
            </button>
            <button type="button" class="secondary small" :disabled="saving" @click="editing = null">
              Cancel
            </button>
            <!-- Asks first (the dots say so); in this diet's own form, so
                 it needs no name of its own. -->
            <button type="button" class="secondary small remove-diet" :disabled="saving" @click="remove(d)">
              Remove…
            </button>
          </div>
        </form>
      </li>
    </ul>
    <p v-if="note" class="status" role="status">{{ note }}</p>
    <button v-if="!adding" ref="addButton" type="button" class="secondary small add-diet" @click="startAdding">
      Add a diet
    </button>
    <form v-else class="add-form" aria-labelledby="add-diet-title" @submit.prevent="add">
      <h4 id="add-diet-title">Add a diet</h4>
      <label for="new-diet-name">Name</label>
      <input id="new-diet-name" v-model="newName" maxlength="60" required />
      <fieldset>
        <legend>Avoids</legend>
        <label v-for="a in allergenList ?? []" :key="a.key" class="check">
          <input v-model="newPicked" type="checkbox" :value="a.key" /> {{ a.label }}
        </label>
      </fieldset>
      <p v-if="addError" class="error" role="alert">{{ addError }}</p>
      <div class="actions">
        <button type="submit" class="primary small" :disabled="saving">
          {{ saving ? "Adding…" : "Add" }}
        </button>
        <button type="button" class="secondary small" :disabled="saving" @click="stopAdding">Cancel</button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.diet-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 0.4rem;
}
form {
  display: grid;
  gap: 0.375rem;
  justify-items: start;
  padding: 0.75rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
form > label,
legend,
h4 {
  font-weight: 600;
}
h4 {
  margin: 0 0 0.25rem;
  font-size: 1rem;
}
input:not([type="checkbox"]) {
  box-sizing: border-box;
  width: 100%;
  max-width: 20rem;
  min-height: 2.75rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  font: inherit;
}
fieldset {
  border: 0;
  padding: 0;
  margin: 0.375rem 0 0.25rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
  min-width: 0;
}
legend {
  margin-bottom: 0.3rem;
  padding: 0;
}
.error {
  margin: 0;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  width: 100%;
}
/* Apart from Save and Cancel, at the row's other end. */
.remove-diet {
  margin-left: auto;
}
.change {
  margin-left: 0.5rem;
}
.add-diet,
.add-form {
  margin-top: 0.75rem;
}
.status {
  margin: 0.75rem 0 0;
}
</style>
