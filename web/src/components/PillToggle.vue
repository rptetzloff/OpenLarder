<script setup lang="ts">
// A pill-shaped toggle button (Ray's cleanup pass, 2026-11-11): "Want to
// cook", "Cooked", "On my shelf". Filled when pressed; pressing it again
// undoes it. The label never changes, so nothing moves.
defineProps<{ pressed: boolean; icon: "bookmark" | "check"; disabled?: boolean; label?: string }>();
defineEmits<{ toggle: [] }>();
</script>

<template>
  <button
    type="button"
    class="pill-toggle"
    :aria-pressed="pressed"
    :aria-label="label"
    :disabled="disabled"
    @click="$emit('toggle')"
  >
    <svg v-if="icon === 'bookmark'" viewBox="0 0 16 20" aria-hidden="true" class="filled">
      <path d="M3 2.5h10v15l-5-4-5 4z" />
    </svg>
    <svg v-else viewBox="0 0 20 20" aria-hidden="true">
      <path d="M4 10.5l4 4 8-9" />
    </svg>
    <slot />
  </button>
</template>

<style scoped>
.pill-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  /* A target of 44px, for a thumb. */
  min-height: 2.75rem;
  padding: 0 1.125rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: transparent;
  color: var(--fg);
  font: inherit;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
}
.pill-toggle:hover {
  border-color: var(--fg);
}
.pill-toggle[aria-pressed="true"] {
  border-color: var(--accent);
  background: var(--accent);
  color: var(--on-accent);
}
.pill-toggle:disabled {
  opacity: 0.45;
  cursor: default;
}
svg {
  width: 1.125rem;
  height: 1.125rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.75;
  stroke-linejoin: round;
  stroke-linecap: round;
}
svg.filled {
  width: 0.875rem;
}
.pill-toggle[aria-pressed="true"] .filled {
  fill: currentColor;
}
</style>
