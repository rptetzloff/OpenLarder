<script setup lang="ts">
import { ref, watch } from "vue";
import OptionList from "./OptionList.vue";
import { type IngredientSummary, listIngredients, type Named } from "../ingredients";

// Type to find an ingredient, then pick one; the parent decides what picking
// does (merge into it, put this under it, …).
const props = defineProps<{
  inputId: string;
  label: string;
  placeholder: string;
  exclude: string[];
  disabled?: boolean;
}>();
const emit = defineEmits<{ pick: [ingredient: Named] }>();

const query = ref("");
const candidates = ref<IngredientSummary[]>([]);
// The search they answer, so "no match" waits for the answer.
const answered = ref("");
let asked = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
watch(query, () => {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const mine = ++asked;
    const q = query.value.trim();
    const found = q ? (await listIngredients(q).catch(() => null))?.ingredients : [];
    if (mine === asked && found) {
      candidates.value = found.filter((i) => !props.exclude.includes(i.id)).slice(0, 8);
      answered.value = q;
    }
  }, 200);
});

function pick(c: Named) {
  emit("pick", { id: c.id, name: c.name });
  query.value = "";
  candidates.value = [];
  answered.value = "";
}
</script>

<template>
  <div class="isbn-form">
    <label :for="inputId">{{ label }}</label>
    <div class="row">
      <input
        :id="inputId"
        v-model="query"
        type="search"
        autocomplete="off"
        :placeholder="placeholder"
      />
    </div>
    <OptionList
      v-slot="{ option: c }"
      :options="candidates"
      :for="inputId"
      :disabled="disabled"
      @pick="pick"
    >
      {{ c.name }}
      <span class="page-ref">
        {{ c.recipes.toLocaleString() }} {{ c.recipes === 1 ? "recipe" : "recipes" }}
      </span>
    </OptionList>
    <p v-if="!candidates.length && answered && answered === query.trim()" class="status">
      No other ingredient matches.
    </p>
  </div>
</template>
