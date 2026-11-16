<script setup lang="ts">
import { ref, watch } from "vue";
import OptionList from "./OptionList.vue";
import { type EquipmentSummary, listEquipment, type Related } from "../equipment";

// Type to find a piece of equipment, then pick one; the parent decides what
// picking does (merge into it, count this as it, …). As IngredientPicker,
// over the other list. What any kitchen has is among the choices, and
// says so: a thing can be merged into one, or count as one.
const props = defineProps<{
  inputId: string;
  label: string;
  placeholder: string;
  exclude: string[];
  disabled?: boolean;
}>();
const emit = defineEmits<{ pick: [equipment: Related] }>();

const query = ref("");
const candidates = ref<EquipmentSummary[]>([]);
// The search they answer, so "no match" waits for the answer.
const answered = ref("");
let asked = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
watch(query, () => {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const mine = ++asked;
    const q = query.value.trim();
    const found = q
      ? (await listEquipment(q, 0, { assumed: true }).catch(() => null))?.equipment
      : [];
    if (mine === asked && found) {
      candidates.value = found.filter((e) => !props.exclude.includes(e.id)).slice(0, 8);
      answered.value = q;
    }
  }, 200);
});

function pick(c: Related) {
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
      <span v-if="c.assumed" class="page-ref">expected in any kitchen</span>
    </OptionList>
    <p v-if="!candidates.length && answered && answered === query.trim()" class="status">
      No other equipment matches.
    </p>
  </div>
</template>
