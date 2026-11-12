<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { chooseGrocer, grocerNow, grocers, loadGrocers } from "../grocery";

// Which grocer ingredients' "Shop" links go to; shown only while a grocer
// is on offer. The page says the commission beside it.
const props = defineProps<{ signedIn: boolean }>();
const error = ref("");
const now = computed(() => grocerNow());

onMounted(loadGrocers);

async function change(event: Event) {
  error.value = "";
  try {
    await chooseGrocer((event.target as HTMLSelectElement).value, props.signedIn);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}
</script>

<template>
  <div v-if="now" class="grocer-chooser">
    <label v-if="grocers!.length > 1">
      Shop at
      <select :value="now.key" @change="change">
        <option v-for="g in grocers" :key="g.key" :value="g.key">{{ g.label }}</option>
      </select>
    </label>
    <span v-else class="muted">Shop links go to {{ now.label }}.</span>
    <span v-if="error" class="error" role="alert">{{ error }}</span>
  </div>
</template>

<style scoped>
.grocer-chooser {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.25rem 1rem;
  font-size: var(--text-sm);
}
.grocer-chooser select {
  font: inherit;
  margin-left: 0.25rem;
  min-height: 2.75rem;
  padding: 0.2rem 0.4rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
}
</style>
