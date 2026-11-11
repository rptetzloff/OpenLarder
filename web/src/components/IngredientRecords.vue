<script setup lang="ts">
import { ref, watch } from "vue";
import { DATA_TYPES, type Food, findFoods, type Ingredient, setLinks } from "../ingredients";

// The same food in USDA FoodData Central and Wikidata, both public domain
// (CC0); moderators link and unlink them here (fdc.py).
const props = defineProps<{ ingredient: Ingredient; canEdit: boolean }>();
const emit = defineEmits<{ changed: [] }>();

// The closest, to choose from; more words narrow them.
const SHOWN = 12;
const editing = ref(false);
const food = ref<Food | null>(null);
const wikidata = ref("");
const q = ref("");
const found = ref<Food[] | null>(null);
const searching = ref(false);
const searchError = ref("");
const saving = ref(false);
const error = ref("");

function start() {
  food.value = props.ingredient.fdc;
  wikidata.value = props.ingredient.wikidata?.id ?? "";
  q.value = props.ingredient.fdc ? "" : props.ingredient.name;
  found.value = null;
  error.value = "";
  editing.value = true;
  if (q.value) search();
}

let timer: ReturnType<typeof setTimeout> | undefined;
let asked = 0;
async function search() {
  const words = q.value.trim();
  if (!words) {
    found.value = null;
    return;
  }
  const mine = ++asked;
  searching.value = true;
  searchError.value = "";
  try {
    const foods = await findFoods(words);
    if (mine === asked) found.value = foods;
  } catch (e) {
    if (mine === asked) searchError.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (mine === asked) searching.value = false;
  }
}
watch(q, () => {
  clearTimeout(timer);
  timer = setTimeout(search, 300);
});

async function save() {
  saving.value = true;
  error.value = "";
  try {
    await setLinks(props.ingredient.id, food.value?.fdc_id ?? null, wikidata.value.trim());
    editing.value = false;
    emit("changed");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <section
    v-if="canEdit || ingredient.fdc || ingredient.wikidata"
    class="source-section ingredient-records"
    aria-labelledby="records-title"
  >
    <div class="table-head">
      <h2 id="records-title">The same food elsewhere</h2>
      <button v-if="canEdit && !editing" type="button" class="link" @click="start">
        {{ ingredient.fdc || ingredient.wikidata ? "Change" : "+ Link" }}
      </button>
    </div>
    <template v-if="!editing">
      <dl class="records">
        <div>
          <dt>USDA FoodData Central</dt>
          <dd v-if="ingredient.fdc">
            <a :href="ingredient.fdc.url" rel="noopener">{{ ingredient.fdc.description }}</a>
            <span class="muted">
              · {{ DATA_TYPES[ingredient.fdc.data_type]
              }}<template v-if="ingredient.fdc.category"> · {{ ingredient.fdc.category }}</template>
            </span>
          </dd>
          <dd v-else class="status">Not linked yet.</dd>
        </div>
        <div>
          <dt>Wikidata</dt>
          <dd v-if="ingredient.wikidata">
            <a :href="ingredient.wikidata.url" rel="noopener">{{
              ingredient.wikidata.label ?? ingredient.wikidata.id
            }}</a>
            <span class="muted"> · {{ ingredient.wikidata.id }}</span>
          </dd>
          <dd v-else class="status">Not linked yet.</dd>
        </div>
      </dl>
      <p v-if="ingredient.same_records.length" class="status">
        Also linked to the same:
        <template v-for="(s, i) in ingredient.same_records" :key="s.id"
          ><template v-if="i > 0">, </template><a :href="`/ingredients/${s.id}`">{{ s.name }}</a></template
        >. Probably the same ingredient<template v-if="canEdit">: merge it from below</template>.
      </p>
    </template>

    <form v-else class="records-form" @submit.prevent="save">
      <fieldset>
        <legend>USDA FoodData Central</legend>
        <p v-if="food" class="chosen">
          <a :href="food.url" rel="noopener">{{ food.description }}</a>
          <span class="muted"> · {{ DATA_TYPES[food.data_type] }} · {{ food.fdc_id }}</span>
          <button type="button" class="link" @click="food = null">Unlink</button>
        </p>
        <label for="fdc-q">Find a food, by words or its FDC ID</label>
        <input id="fdc-q" v-model="q" autocomplete="off" maxlength="200" />
        <p v-if="searchError" class="error" role="alert">{{ searchError }}</p>
        <p v-else-if="searching" class="status" aria-live="polite">Searching…</p>
        <p v-else-if="found && !found.length" class="status" aria-live="polite">
          No foods found. If none are loaded yet, an administrator loads them from Admin.
        </p>
        <ul v-if="found?.length" class="food-results" aria-label="Foods found">
          <li v-for="f in found.slice(0, SHOWN)" :key="f.fdc_id">
            <label>
              <input
                type="radio"
                name="fdc-food"
                :checked="food?.fdc_id === f.fdc_id"
                @change="food = f"
              />
              <span>
                {{ f.description }}
                <span class="muted"
                  >· {{ DATA_TYPES[f.data_type]
                  }}<template v-if="f.category"> · {{ f.category }}</template></span
                >
              </span>
            </label>
            <a :href="f.url" rel="noopener" :aria-label="`View ${f.description} at FoodData Central`"
              >View</a
            >
          </li>
        </ul>
      </fieldset>
      <fieldset>
        <legend>Wikidata</legend>
        <label for="wikidata-item">Its item: an ID like Q23485, or a link to it</label>
        <input id="wikidata-item" v-model="wikidata" maxlength="300" autocomplete="off" />
        <p class="muted">Empty unlinks it.</p>
      </fieldset>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="actions">
        <button type="submit" class="primary" :disabled="saving">
          {{ saving ? "Saving…" : "Save" }}
        </button>
        <button type="button" class="secondary" :disabled="saving" @click="editing = false">
          Cancel
        </button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.records {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 0.75rem 2rem;
  margin: 0 0 0.75rem;
}
.records dt {
  font-weight: 600;
}
.records dd {
  margin: 0.15rem 0 0;
  overflow-wrap: anywhere;
}
.records-form fieldset {
  border: 0;
  padding: 0;
  margin: 0 0 1rem;
  min-width: 0;
}
.records-form legend {
  font-weight: 600;
  margin-bottom: 0.4rem;
}
.records-form label {
  display: block;
  margin-bottom: 0.25rem;
}
.records-form input:not([type="radio"]) {
  font: inherit;
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  box-sizing: border-box;
  width: 100%;
  max-width: 32rem;
}
.chosen {
  overflow-wrap: anywhere;
}
.food-results {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0 0;
  display: grid;
  gap: 0.4rem;
}
.food-results li {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  max-width: 40rem;
}
.food-results label {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  margin: 0;
  overflow-wrap: anywhere;
}
.actions {
  display: flex;
  gap: 0.75rem;
}
</style>
