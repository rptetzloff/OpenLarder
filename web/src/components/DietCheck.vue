<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { list as allergenList, loadAllergens } from "../allergens";
import { checkDiet, type Diet, type DietCheck, listDiets } from "../substitutions";

// Cooking this recipe for a diet: its ingredients that record an allergen
// the diet avoids, and the swaps recorded for them (diets.py). Never says
// the recipe suits the diet.
// noticeAbove: the page shows the allergen notice just above already.
const props = defineProps<{ recipeId: string; noticeAbove?: boolean }>();

const diets = ref<Diet[]>([]);
const chosen = ref("");
const result = ref<DietCheck | null>(null);
const loading = ref(false);
const error = ref("");

onMounted(async () => {
  loadAllergens();
  try {
    diets.value = (await listDiets()).filter((d) => d.avoids.length);
  } catch {
    diets.value = [];
  }
});

const labels = computed(
  () => Object.fromEntries((allergenList.value ?? []).map((a) => [a.key, a.label])) as Record<string, string>,
);
const checks = computed(() =>
  (result.value?.diet.avoids ?? []).map((k) => (labels.value[k] ?? k).toLowerCase()),
);

function listed(words: string[]) {
  if (words.length < 2) return words.join("");
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

async function check() {
  result.value = null;
  error.value = "";
  if (!chosen.value) return;
  loading.value = true;
  try {
    result.value = await checkDiet(props.recipeId, chosen.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <section v-if="diets.length" class="recipe-section diet-check" aria-labelledby="diet-check-title">
    <h2 id="diet-check-title">Cooking for a diet</h2>
    <label class="diet-choice">
      Diet
      <select v-model="chosen" @change="check">
        <option value="">Choose one</option>
        <option v-for="d in diets" :key="d.id" :value="d.id">{{ d.name }}</option>
      </select>
    </label>
    <p v-if="loading" class="status" aria-live="polite">Checking…</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="result" aria-live="polite">
      <p class="muted">
        {{ result.diet.name }} here means checking for {{ listed(checks) }}, and nothing else.
      </p>
      <p v-if="!result.lines.length" class="status">
        No ingredient here records {{ listed(checks) }}.
      </p>
      <ul v-else class="ingredient-lines diet-lines">
        <li v-for="line in result.lines" :key="line.ingredient.id">
          <p>
            <a :href="`/ingredients/${line.ingredient.id}`">{{ line.ingredient.name }}</a>
            <span class="muted">
              ·
              {{
                line.found
                  .map((f) => `${f.status === "contains" ? "contains" : "may contain"} ${f.label.toLowerCase()}`)
                  .join(", ")
              }}</span
            >
          </p>
          <ul v-if="line.swaps.length" class="diet-swaps">
            <li v-for="s in line.swaps" :key="s.id">
              Use
              <a :href="`/${s.use.kind === 'ingredient' ? 'ingredients' : 'recipes'}/${s.use.id}`">{{
                s.use.name
              }}</a>
              instead<template v-if="s.instead_of.id !== line.ingredient.id">
                of {{ s.instead_of.name.toLowerCase() }}</template
              ><span class="muted">
                · for {{ s.diet?.name
                }}<template v-if="s.source">
                  · <a :href="`/sources/${s.source.source_id}`">{{ s.source.source_title }}</a
                  ><template v-if="s.source.page">, p. {{ s.source.page }}</template></template
                ></span
              ><template v-if="s.note"> — {{ s.note }}</template>
            </li>
          </ul>
          <p v-else class="status">No swap recorded for it yet.</p>
        </li>
      </ul>
      <p v-if="noticeAbove" class="allergen-notice">
        As above: only what the catalog records, which is no guarantee.
      </p>
      <p v-else class="allergen-notice">
        Only what the catalog records about these ingredients: one with nothing recorded may still
        contain any allergen. {{ result.notice }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.diet-choice select {
  font: inherit;
  margin-left: 0.4rem;
  padding: 0.25rem 0.4rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
}
.diet-choice {
  display: inline-block;
  margin-bottom: 0.75rem;
}
.diet-lines p {
  margin: 0;
}
.diet-swaps {
  margin: 0.3rem 0 0;
  padding-left: 1.25rem;
}
</style>
