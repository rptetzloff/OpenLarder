<script setup lang="ts" generic="T extends string">
// One choice among a few, over a list: a reason, a role, a kind. Buttons in
// a row where there's room; on a phone one select, a line where the buttons
// were two or three rows (Ray's round 4 list, B5 and B6, 2026-11-14, for
// Flagged recipes and People; Suggestions and Ingredient links have it too,
// which he didn't ask and their pages needed). Only one of the two is drawn,
// so only one is there for a keyboard or a screen reader.
const model = defineModel<T>({ required: true });
defineProps<{
  label: string;
  // For the select and its label.
  id: string;
  options: { value: T; label: string; count?: string }[];
  // None of them is the one in use: the list is by something else just now.
  none?: boolean;
}>();
// The button already pressed was pressed again.
const emit = defineEmits<{ again: [value: T] }>();
</script>

<template>
  <div class="filter-choice">
    <div class="kind-filter" role="group" :aria-label="label">
      <button
        v-for="o in options"
        :key="o.value"
        type="button"
        class="secondary small"
        :aria-pressed="!none && model === o.value"
        @click="!none && model === o.value ? emit('again', o.value) : (model = o.value)"
      >
        {{ o.label }}<span v-if="o.count !== undefined" class="count">{{ o.count }}</span>
      </button>
    </div>
    <div class="filter-select">
      <label :for="id">{{ label }}</label>
      <select :id="id" v-model="model">
        <option v-for="o in options" :key="o.value" :value="o.value">
          {{ o.label }}{{ o.count !== undefined ? ` (${o.count})` : "" }}
        </option>
      </select>
    </div>
  </div>
</template>

<style scoped>
.filter-select {
  display: none;
}
@media (max-width: 40rem) {
  .kind-filter {
    display: none;
  }
  .filter-select {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }
  /* The label keeps its word whole; a long choice shortens the select. */
  .filter-select label {
    flex: none;
    font-weight: 600;
  }
  .filter-select select {
    flex: 0 1 auto;
    min-width: 0;
    text-overflow: ellipsis;
    max-width: 100%;
    min-height: 2.75rem;
    padding: 0.375rem 0.625rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
    color: var(--fg);
    font: inherit;
  }
}
</style>
