<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import AdminBand from "../components/AdminBand.vue";
import Crumbs from "../components/Crumbs.vue";
import EquipmentPicker from "../components/EquipmentPicker.vue";
import HistoryPanel from "../components/HistoryPanel.vue";
import ReportButton from "../components/ReportButton.vue";
import {
  addAlias,
  countAs,
  deleteAlias,
  deleteEquipment,
  type Equipment,
  fetchEquipment,
  mergeEquipment,
  type Related,
  renameEquipment,
  setAssumed,
  stopCountingAs,
  Taken,
} from "../equipment";
import { whereItIs } from "../ingredients";
import type { Me } from "../me";

// One piece of equipment: what it is called, what it counts as and what
// counts as it; for a moderator, the tools that change those (Ray's spec,
// 2026-11-15: rename, merge into, count as, also called, mark as any
// kitchen's, delete when unused), as an ingredient's page has its own.
// Under them, the recipes that need it, with what counts as it unless only
// this exact thing is asked for. The button to search with it comes with
// search's filter, and the one to shop for it with the shop links: nothing
// here that doesn't work yet.
const props = defineProps<{ id: string; user: Me | null | undefined }>();
const equipment = ref<Equipment | null>(null);
const missing = ref(false);
const failed = ref(false);

const loading = ref(false);
// The recipes needing anything that counts as it too, unless only this
// exact thing is asked for, as an ingredient's page has it.
const exact = ref(false);
const hasNarrower = computed(() => !!equipment.value?.includes.length);

async function load(more = false) {
  loading.value = true;
  try {
    const offset = more ? (equipment.value?.recipes.length ?? 0) : 0;
    const found = await fetchEquipment(props.id, offset, !exact.value);
    if (found === null) missing.value = true;
    else if (more && equipment.value) equipment.value.recipes.push(...found.recipes);
    else {
      equipment.value = found;
      newName.value = found.name;
      document.title = `${found.name} · Equipment · OpenLarder`;
    }
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

// Where a listed recipe is in its source, without the authors the table's
// Source column doesn't need.
function where(r: Equipment["recipes"][number]) {
  return whereItIs({ ...r, authors: [] }) || "—";
}

// Fixing it, for moderators.

const newName = ref("");
const otherName = ref("");
const error = ref("");
// Set when a name typed is another thing's, to offer merging into it.
const taken = ref<Related | null>(null);
const busy = ref(false);

// Runs one change, then shows the page as it is now; what's refused is
// said above the tools.
async function change(what: () => Promise<unknown>) {
  error.value = "";
  taken.value = null;
  busy.value = true;
  try {
    await what();
    await load();
    return true;
  } catch (e) {
    if (e instanceof Taken) taken.value = e.equipment;
    error.value = e instanceof Error ? e.message : String(e);
    return false;
  } finally {
    busy.value = false;
  }
}

const rename = () => {
  const here = equipment.value;
  if (here && newName.value.trim()) change(() => renameEquipment(here.id, newName.value));
};

async function alsoCall() {
  const here = equipment.value;
  if (!here || !otherName.value.trim()) return;
  if (await change(() => addAlias(here.id, otherName.value))) otherName.value = "";
}

async function removeAlias(alias: Related) {
  const here = equipment.value;
  const message =
    `Stop finding “${here?.name}” by “${alias.name}”?\n\n` +
    "A recipe that already lists it keeps it.";
  if (!here || !confirm(message)) return;
  change(() => deleteAlias(here.id, alias.id));
}

async function merge(into: Related) {
  const here = equipment.value;
  if (!here) return;
  const n = here.total;
  const needing = n === 1 ? "The recipe that lists it" : `The ${n.toLocaleString()} recipes that list it`;
  const message =
    `Merge “${here.name}” into “${into.name}”?\n\n` +
    `${n ? `${needing} will list “${into.name}”, and ` : ""}` +
    `“${here.name}” will be another name for it.`;
  if (!confirm(message)) return;
  error.value = "";
  busy.value = true;
  try {
    const left = await mergeEquipment(here.id, into.id);
    location.href = `/equipment/${left.id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    busy.value = false;
  }
}

async function remove() {
  const here = equipment.value;
  if (!here || !confirm(`Delete “${here.name}”? No recipe lists it.`)) return;
  error.value = "";
  try {
    await deleteEquipment(here.id);
    location.href = "/equipment";
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

onMounted(() => load());
</script>

<template>
  <article class="wide equipment-page">
    <p v-if="missing">There's no equipment here. It may have been merged into another.</p>
    <p v-else-if="failed" role="alert">This equipment couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!equipment" class="status">Loading…</p>
    <template v-else>
      <AdminBand v-if="user?.may_edit" id="admin-here" label="This equipment" before="Admin: ">
        <a href="#equipment-name">Rename</a>
        <a href="#merge-into">Merge into…</a>
        <a href="#counts-as">Count it as…</a>
        <a href="#other-name">Add another name</a>
        <a href="#any-kitchen">{{
          equipment.assumed ? "Let recipes list it" : "Mark as any kitchen's"
        }}</a>
        <a
          v-if="equipment.total === 0 && !equipment.includes.length"
          href="#delete-equipment"
          >Delete</a
        >
        <span v-else class="muted">Delete (only when nothing uses it)</span>
      </AdminBand>

      <Crumbs :trail="[{ href: '/equipment', label: 'Equipment' }]" />

      <div class="ingredient-head">
        <div>
          <h1>{{ equipment.name }}</h1>
          <p v-if="equipment.assumed" class="status">
            Expected in any kitchen, so recipes don't list it.
          </p>
          <p v-else-if="equipment.family_total" class="status">
            Needed for {{ equipment.family_total.toLocaleString() }}
            {{ equipment.family_total === 1 ? "recipe" : "recipes"
            }}{{ equipment.includes.length ? ", including everything it includes" : "" }}
          </p>
          <p v-else class="status">No recipe lists it yet.</p>
        </div>
      </div>

      <!-- As an ingredient's page: one line when there's nothing to say,
           and otherwise a card for each thing there is. -->
      <p
        v-if="!equipment.counts_as.length && !equipment.includes.length && !equipment.aliases.length"
        class="status no-relations"
      >
        Nothing it counts as, includes or is also called yet.
      </p>
      <div v-else class="ingredient-cards">
        <div v-if="equipment.counts_as.length">
          <h2>Counts as</h2>
          <p>
            <template v-for="(c, i) in equipment.counts_as" :key="c.id"
              ><template v-if="i > 0"> · </template
              ><a :href="`/equipment/${c.id}`">{{ c.name }}</a></template
            >
          </p>
        </div>
        <div v-if="equipment.includes.length">
          <h2>Includes</h2>
          <p>
            <template v-for="(c, i) in equipment.includes" :key="c.id"
              ><template v-if="i > 0"> · </template
              ><a :href="`/equipment/${c.id}`">{{ c.name }}</a></template
            >
          </p>
        </div>
        <div v-if="equipment.aliases.length">
          <h2>Also called</h2>
          <p>
            <template v-for="(a, i) in equipment.aliases" :key="a.id"
              ><template v-if="i > 0"> · </template>{{ a.name }}</template
            >
          </p>
        </div>
      </div>

      <section v-if="!equipment.assumed && equipment.family_total" class="source-section">
        <div class="table-head">
          <h2>Recipes needing {{ equipment.name.toLowerCase() }}</h2>
          <label v-if="hasNarrower" class="check"
            ><input v-model="exact" type="checkbox" @change="load()" /> Only this exact thing</label
          >
        </div>
        <table v-if="equipment.recipes.length" class="recipe-table uses-table">
          <thead>
            <tr>
              <th scope="col">Recipe</th>
              <th scope="col">Source</th>
              <th scope="col">Where</th>
              <th scope="col">Need as listed</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in equipment.recipes" :key="r.id">
              <td><a :href="`/recipes/${r.id}`" class="strong">{{ r.title }}</a></td>
              <td class="uses-source"><a :href="`/sources/${r.source_id}`">{{ r.source_title }}</a></td>
              <td class="muted uses-where">{{ where(r) }}</td>
              <td class="lines">{{ r.line }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="status">No recipe lists exactly this.</p>
        <button
          v-if="equipment.recipes.length < equipment.listed_total"
          type="button"
          class="secondary show-more"
          :disabled="loading"
          @click="load(true)"
        >
          Show more ({{ (equipment.listed_total - equipment.recipes.length).toLocaleString() }}
          left)
        </button>
      </section>

      <section v-if="user?.may_edit" class="fix-ingredient source-section">
        <h2>Fix this equipment</h2>
        <p v-if="error" class="error" role="alert">
          {{ error }}
          <template v-if="taken">
            <button type="button" class="secondary small" :disabled="busy" @click="merge(taken)">
              Merge into “{{ taken.name }}”
            </button>
          </template>
        </p>

        <form class="isbn-form" @submit.prevent="rename">
          <label for="equipment-name">Name</label>
          <div class="row">
            <input id="equipment-name" v-model="newName" required autocomplete="off" />
            <button
              type="submit"
              class="primary"
              :disabled="busy || newName.trim() === equipment.name"
            >
              Rename
            </button>
          </div>
        </form>

        <EquipmentPicker
          input-id="merge-into"
          label="Merge into another piece of equipment"
          placeholder="the one to keep"
          :exclude="[equipment.id]"
          :disabled="busy"
          @pick="merge"
        />

        <h3>What it counts as</h3>
        <p class="status">
          Having a thing covers a recipe that needs anything it counts as: a stand mixer counts as
          a mixer. It can count as more than one.
        </p>
        <p v-if="equipment.counts_as.length" class="status">
          Counts as now:
          <template v-for="c in equipment.counts_as" :key="c.id">
            <span class="with-remove"
              >{{ c.name }}
              <button
                type="button"
                class="remove"
                :disabled="busy"
                :aria-label="`Stop counting it as ${c.name}`"
                @click="change(() => stopCountingAs(equipment!.id, c.id))"
              >
                ×
              </button>
            </span>
          </template>
        </p>
        <EquipmentPicker
          input-id="counts-as"
          :label="equipment.counts_as.length ? 'Count it as something else too' : 'Count it as'"
          placeholder="mixer"
          :exclude="[equipment.id, ...equipment.counts_as.map((c) => c.id)]"
          :disabled="busy"
          @pick="(p) => change(() => countAs(equipment!.id, p.id))"
        />
        <EquipmentPicker
          input-id="includes"
          label="Add something that counts as this"
          placeholder="stand mixer"
          :exclude="[
            equipment.id,
            ...equipment.includes.map((c) => c.id),
            ...equipment.counts_as.map((c) => c.id),
          ]"
          :disabled="busy"
          @pick="(c) => change(() => countAs(c.id, equipment!.id))"
        />
        <p v-if="equipment.includes.length" class="status">
          Includes now:
          <template v-for="c in equipment.includes" :key="c.id">
            <span class="with-remove"
              >{{ c.name }}
              <button
                type="button"
                class="remove"
                :disabled="busy"
                :aria-label="`Stop counting ${c.name} as this`"
                @click="change(() => stopCountingAs(c.id, equipment!.id))"
              >
                ×
              </button>
            </span>
          </template>
        </p>

        <h3>What it's also called</h3>
        <p class="status">A name typed for a recipe finds it by any of these.</p>
        <p v-if="equipment.aliases.length" class="status">
          Also called now:
          <template v-for="a in equipment.aliases" :key="a.id">
            <span class="with-remove"
              >{{ a.name }}
              <button
                type="button"
                class="remove"
                :disabled="busy"
                :aria-label="`Stop calling it ${a.name}`"
                @click="removeAlias(a)"
              >
                ×
              </button>
            </span>
          </template>
        </p>
        <form class="isbn-form" @submit.prevent="alsoCall">
          <label for="other-name">Another name for it</label>
          <div class="row">
            <input id="other-name" v-model="otherName" autocomplete="off" placeholder="stick blender" />
            <button type="submit" class="secondary" :disabled="busy || !otherName.trim()">
              Add the name
            </button>
          </div>
        </form>

        <h3>Whether any kitchen has it</h3>
        <p v-if="equipment.assumed" class="status">
          Expected in any kitchen, so it can't be put on a recipe.
        </p>
        <p v-else class="status">
          A recipe can list it. What any kitchen has (a knife, a mixing bowl) is never listed.
        </p>
        <p>
          <button
            id="any-kitchen"
            type="button"
            class="secondary small"
            :disabled="busy"
            @click="change(() => setAssumed(equipment!.id, !equipment!.assumed))"
          >
            {{ equipment.assumed ? "Let recipes list it" : "Mark as expected in any kitchen" }}
          </button>
        </p>

        <p v-if="equipment.total === 0 && !equipment.includes.length">
          <button id="delete-equipment" type="button" class="secondary small" @click="remove">
            Delete this equipment
          </button>
        </p>
      </section>
      <!-- As an ingredient's page has (Ray, 2026-11-16: treated the same). -->
      <ReportButton kind="equipment" :id="id" />
      <HistoryPanel kind="equipment" :id="id" :can-revert="!!user?.may_edit" />
    </template>
  </article>
</template>
