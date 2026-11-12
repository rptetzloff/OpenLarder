<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";

// A header menu (Ray's cleanup pass, section 3): a disclosure button that
// opens a list of links. Esc closes it and gives focus back to the button;
// so does a click elsewhere, or tabbing out. Plain links in a list, so no
// menu role is needed.
defineProps<{
  label: string;
  // The panel's id, for aria-controls.
  id: string;
  // Drawn as an outlined button.
  outlined?: boolean;
  // The panel spans the header's width, under it: the phone's menu.
  full?: boolean;
}>();

const open = ref(false);
const root = ref<HTMLElement | null>(null);
const button = ref<HTMLButtonElement | null>(null);

function close(refocus = false) {
  if (!open.value) return;
  open.value = false;
  if (refocus) button.value?.focus();
}
function onClickAway(event: MouseEvent) {
  if (root.value && !root.value.contains(event.target as Node)) close();
}
// Focus has gone somewhere outside it.
function onFocusOut(event: FocusEvent) {
  const to = event.relatedTarget as Node | null;
  if (to && root.value && !root.value.contains(to)) close();
}
onMounted(() => document.addEventListener("click", onClickAway));
onBeforeUnmount(() => document.removeEventListener("click", onClickAway));
</script>

<template>
  <div ref="root" class="menu" :class="{ full }" @keydown.esc="close(true)" @focusout="onFocusOut">
    <button
      ref="button"
      type="button"
      :class="{ outlined }"
      :aria-expanded="open"
      :aria-controls="id"
      @click="open = !open"
    >
      {{ label }}
      <svg viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4" /></svg>
    </button>
    <div v-show="open" :id="id" class="panel">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.menu {
  position: relative;
}
/* The phone's menu hangs from the header's bar, not the button. */
.menu.full {
  position: static;
}
button {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  min-height: 2.75rem;
  padding: 0 0.875rem;
  border: 1px solid transparent;
  border-radius: var(--radius);
  background: none;
  color: var(--fg);
  font: inherit;
  font-weight: 500;
  cursor: pointer;
}
button.outlined {
  border-color: var(--border);
}
button:hover,
button[aria-expanded="true"] {
  border-color: var(--fg);
}
svg {
  width: 0.625rem;
  height: 0.375rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.panel {
  position: absolute;
  top: calc(100% + 0.25rem);
  right: 0;
  z-index: 20;
  min-width: 11rem;
  padding: 0.375rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: 0 6px 20px rgb(0 0 0 / 12%);
}
.menu.full .panel {
  top: 100%;
  left: 0;
  right: 0;
  border-width: 1px 0;
  border-radius: 0;
  padding: 0.5rem 1rem 1rem;
}
/* What goes in it: lists of links, and the sign-out button, each a row. */
.panel :deep(ul) {
  list-style: none;
  margin: 0;
  padding: 0;
}
.panel :deep(h2) {
  margin: 0.75rem 0 0.125rem;
  padding: 0 0.625rem;
  color: var(--muted);
  font-size: var(--text-xs);
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.panel :deep(form) {
  margin: 0;
}
.panel :deep(a),
.panel :deep(button) {
  display: flex;
  align-items: center;
  box-sizing: border-box;
  width: 100%;
  min-height: 2.75rem;
  padding: 0 0.625rem;
  border: 0;
  border-radius: var(--radius);
  background: none;
  color: var(--fg);
  font: inherit;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}
.panel :deep(a:hover),
.panel :deep(button:hover) {
  background: var(--bg);
}
.panel :deep(a[aria-current="page"]) {
  font-weight: 700;
}
</style>
