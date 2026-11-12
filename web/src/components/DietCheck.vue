<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { list as allergenList, loadAllergens } from "../allergens";
import { checkDiet, type Diet, type DietCheck, listDiets } from "../substitutions";

// Cooking this recipe for a diet: its ingredients that record an allergen
// the diet avoids, and the swaps recorded for them (diets.py); and what the
// diet avoids only together (Kosher's meat with milk), found across the
// recipe. Never says the recipe suits the diet.
// A card in the recipe page's sidebar (Ray's cleanup pass, section 2).
// noticeShown: the page shows the full allergen notice already.
const props = defineProps<{ recipeId: string; noticeShown?: boolean }>();

const diets = ref<Diet[]>([]);
const chosen = ref("");
const result = ref<DietCheck | null>(null);
const loading = ref(false);
const error = ref("");

onMounted(async () => {
  loadAllergens();
  try {
    diets.value = (await listDiets()).filter((d) => d.avoids.length || d.together.length);
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

function listed(words: string[], and = "and") {
  if (words.length < 2) return words.join("");
  return `${words.slice(0, -1).join(", ")} ${and} ${words[words.length - 1]}`;
}
const label = (key: string) => (labels.value[key] ?? key).toLowerCase();
// "meat or poultry together with milk", one for each thing they go with.
const pairs = computed(() => {
  const by = new Map<string, string[]>();
  for (const p of result.value?.diet.together ?? []) {
    by.set(p.other, [...(by.get(p.other) ?? []), label(p.allergen)]);
  }
  return [...by].map(([other, keys]) => `${listed(keys, "or")} together with ${label(other)}`);
});
// What the diet means here, in words.
const meaning = computed(() =>
  [checks.value.length ? listed(checks.value) : "", ...pairs.value].filter(Boolean).join(", and for "),
);
const names = (has: { ingredient: { name: string }; status: string }[]) =>
  has.map((h) => (h.status === "may_contain" ? `${h.ingredient.name} (may)` : h.ingredient.name));

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
  <section v-if="diets.length" class="diet-check" aria-labelledby="diet-check-title">
    <h2 id="diet-check-title">Cooking for a diet</h2>
    <select v-model="chosen" aria-labelledby="diet-check-title" @change="check">
      <option value="">Choose a diet</option>
      <option v-for="d in diets" :key="d.id" :value="d.id">{{ d.name }}</option>
    </select>
    <p v-if="!result && !loading" class="muted diet-help">
      Shows swaps for ingredients a diet avoids. Crowdsourced, not a safety guarantee.
    </p>
    <p v-if="loading" class="status" aria-live="polite">Checking…</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="result" aria-live="polite">
      <p class="muted">
        {{ result.diet.name }} here means checking for {{ meaning }}, and nothing else.
      </p>
      <p v-if="!result.lines.length && !result.together.length" class="status">
        Nothing recorded for this recipe's ingredients is among those.
      </p>
      <ul v-if="result.together.length" class="ingredient-lines diet-lines diet-together">
        <li v-for="t in result.together" :key="`${t.allergen.key}-${t.other.key}`">
          <p>
            <strong>{{ t.allergen.label }} with {{ t.other.label.toLowerCase() }}.</strong>
            {{ t.allergen.label }}:
            <template v-for="(h, i) in t.has" :key="h.ingredient.id"
              ><template v-if="i > 0">, </template
              ><a :href="`/ingredients/${h.ingredient.id}`">{{ names([h])[0] }}</a></template
            >. {{ t.other.label }}:
            <template v-for="(h, i) in t.has_other" :key="h.ingredient.id"
              ><template v-if="i > 0">, </template
              ><a :href="`/ingredients/${h.ingredient.id}`">{{ names([h])[0] }}</a></template
            >.
          </p>
        </li>
      </ul>
      <ul v-if="result.lines.length" class="ingredient-lines diet-lines">
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
      <p v-if="noticeShown" class="allergen-notice">
        Only what the catalog records, which is no guarantee.
      </p>
      <p v-else class="allergen-notice">
        Only what the catalog records about these ingredients: one with nothing recorded may still
        contain any of them. {{ result.notice }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.diet-check {
  padding: 0.875rem 1rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--surface);
  font-size: var(--text-sm);
}
.diet-check h2 {
  margin: 0 0 0.5rem;
  font-size: var(--text-md);
}
.diet-check select {
  font: inherit;
  font-size: var(--text-md);
  width: 100%;
  min-height: 2.75rem;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--fg);
}
.diet-help {
  margin: 0.5rem 0 0;
}
.diet-lines p {
  margin: 0;
}
.diet-swaps {
  margin: 0.3rem 0 0;
  padding-left: 1.25rem;
}
</style>
