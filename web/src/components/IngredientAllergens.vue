<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  list,
  loadAllergens,
  notice,
  setAllergens,
  STATUS_WORDS,
  type Status,
} from "../allergens";
import type { Ingredient } from "../ingredients";

// What an ingredient records about allergens, or inherits from a broader
// one; moderators record them here (allergens.py). Crowdsourced, so the
// notice is always beside them.
const props = defineProps<{ ingredient: Ingredient; canEdit: boolean }>();
const emit = defineEmits<{ changed: [] }>();

const editing = ref(false);
// Allergen: its own status, or "" for nothing recorded here.
const chosen = ref<Record<string, Status | "">>({});
const saving = ref(false);
const error = ref("");

onMounted(loadAllergens);

const own = computed(() => props.ingredient.allergens.filter((a) => !a.inherited));
const inherited = computed(() =>
  Object.fromEntries(
    props.ingredient.allergens.filter((a) => a.inherited).map((a) => [a.key, a]),
  ),
);

function start() {
  chosen.value = Object.fromEntries(
    (list.value ?? []).map((a) => [a.key, own.value.find((o) => o.key === a.key)?.status ?? ""]),
  );
  error.value = "";
  editing.value = true;
}

async function save() {
  saving.value = true;
  error.value = "";
  try {
    const statuses = Object.fromEntries(
      Object.entries(chosen.value).filter(([, s]) => s !== ""),
    ) as Record<string, Status>;
    await setAllergens(props.ingredient.id, statuses);
    editing.value = false;
    emit("changed");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}

function inheritedWords(key: string): string {
  const a = inherited.value[key];
  if (!a) return "None";
  const from = a.inherited_from ? ` from ${a.inherited_from.name}` : " from a broader ingredient";
  return `${STATUS_WORDS[a.status]}${from}`;
}
</script>

<template>
  <section
    v-if="canEdit || ingredient.allergens.length"
    class="source-section ingredient-allergens"
    aria-labelledby="allergens-title"
  >
    <div class="table-head">
      <h2 id="allergens-title">Allergens and meat</h2>
      <button v-if="canEdit && !editing && list?.length" type="button" class="link" @click="start">
        {{ own.length ? "Change" : "+ Record" }}
      </button>
    </div>
    <p class="allergen-notice">{{ notice }}</p>
    <template v-if="!editing">
      <ul v-if="ingredient.allergens.length" class="allergen-list">
        <li v-for="a in ingredient.allergens" :key="a.key">
          <strong>{{ STATUS_WORDS[a.status] }} {{ a.label.toLowerCase() }}</strong>
          <span v-if="a.inherited" class="muted">
            · as
            <a v-if="a.inherited_from" :href="`/ingredients/${a.inherited_from.id}`">{{
              a.inherited_from.name
            }}</a>
            <template v-else>a broader ingredient</template>
            records</span
          >
        </li>
      </ul>
      <p v-else class="status">Nothing recorded yet.</p>
    </template>

    <form v-else class="allergens-form" @submit.prevent="save">
      <p class="muted">
        What {{ ingredient.name.toLowerCase() }} records itself. Narrower ingredients inherit it;
        “Doesn't contain” overrides what a broader one records.
      </p>
      <table class="allergen-table">
        <thead>
          <tr>
            <th scope="col">Allergen or meat</th>
            <th scope="col">Here</th>
            <th scope="col">Inherited</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in list" :key="a.key">
            <th scope="row">
              <label :for="`allergen-${a.key}`">{{ a.label }}</label>
            </th>
            <td>
              <select :id="`allergen-${a.key}`" v-model="chosen[a.key]">
                <option value="">Not recorded here</option>
                <option value="contains">Contains</option>
                <option value="may_contain">May contain</option>
                <option value="free">Doesn't contain</option>
              </select>
            </td>
            <td class="muted">{{ inheritedWords(a.key) }}</td>
          </tr>
        </tbody>
      </table>
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
.allergen-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 0.3rem;
}
.allergen-table {
  border-collapse: collapse;
  margin: 0 0 1rem;
  width: 100%;
  max-width: 40rem;
}
.allergen-table th,
.allergen-table td {
  text-align: left;
  padding: 0.3rem 0.75rem 0.3rem 0;
  vertical-align: middle;
}
.allergen-table tbody th {
  font-weight: 400;
}
.allergen-table select {
  font: inherit;
  padding: 0.25rem 0.4rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  max-width: 100%;
}
.actions {
  display: flex;
  gap: 0.75rem;
}
</style>
