<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { list as allergenList, loadAllergens } from "../allergens";
import { type Diet, listDiets, setDietAllergens } from "../substitutions";

// Which allergens each diet avoids, for "Cooking for a diet" on recipes
// (diets.py); moderators change them here.
const diets = ref<Diet[]>([]);
const editing = ref<string | null>(null);
const picked = ref<string[]>([]);
const saving = ref(false);
const error = ref("");

onMounted(async () => {
  loadAllergens();
  diets.value = await listDiets().catch(() => []);
});

const labels = computed(
  () => Object.fromEntries((allergenList.value ?? []).map((a) => [a.key, a.label])) as Record<string, string>,
);

function start(d: Diet) {
  editing.value = d.id;
  picked.value = [...d.avoids];
  error.value = "";
}

async function save(d: Diet) {
  saving.value = true;
  error.value = "";
  try {
    const updated = await setDietAllergens(d.id, picked.value);
    diets.value = diets.value.map((x) => (x.id === d.id ? updated : x));
    editing.value = null;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
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
      swaps recorded for a diet that avoids them too. A diet avoiding none isn't offered.
    </p>
    <ul class="diet-list">
      <li v-for="d in diets" :key="d.id">
        <template v-if="editing !== d.id">
          <strong>{{ d.name }}</strong>
          <span class="muted">
            ·
            {{ d.avoids.length ? d.avoids.map((k) => labels[k] ?? k).join(", ") : "nothing" }}</span
          >
          <button
            type="button"
            class="link change"
            :aria-label="`Change what ${d.name} avoids`"
            @click="start(d)"
          >
            Change
          </button>
        </template>
        <form v-else @submit.prevent="save(d)">
          <fieldset>
            <legend>{{ d.name }} avoids</legend>
            <label v-for="a in allergenList ?? []" :key="a.key" class="check">
              <input v-model="picked" type="checkbox" :value="a.key" /> {{ a.label }}
            </label>
          </fieldset>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <div class="actions">
            <button type="submit" class="primary small" :disabled="saving">
              {{ saving ? "Saving…" : "Save" }}
            </button>
            <button type="button" class="secondary small" :disabled="saving" @click="editing = null">
              Cancel
            </button>
          </div>
        </form>
      </li>
    </ul>
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
.diet-list fieldset {
  border: 0;
  padding: 0;
  margin: 0 0 0.5rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
  min-width: 0;
}
.diet-list legend {
  font-weight: 600;
  margin-bottom: 0.3rem;
}
.actions {
  display: flex;
  gap: 0.5rem;
}
.change {
  margin-left: 0.5rem;
}
</style>
