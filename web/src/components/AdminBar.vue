<script setup lang="ts">
// The yellow band under the header on admin pages and Sources: every admin
// page they may use, with the one you're on marked. Only rendered for a
// moderator or above; the administrators' pages only for them.
//
// On a phone it is one row: "Admin" and a button naming the page you're on,
// which opens the rest (Ray's round 4 list, B1, 2026-11-14: the thirteen
// links wrapped onto five rows, 157px of every admin page at 384px wide).
import { computed, ref, watch } from "vue";
import type { Me } from "../me";

const props = defineProps<{ current?: string; user: Me }>();

// [href, label, administrators only]
const LINKS = [
  ["/admin", "Overview", false],
  ["/admin/import", "Bulk import", true],
  ["/admin/imports", "Import history", true],
  ["/admin/flags", "Flagged recipes", false],
  ["/admin/review", "Review", false],
  ["/admin/reports", "Reports", false],
  ["/admin/suggestions", "Suggestions", false],
  ["/admin/links", "Ingredient links", false],
  ["/admin/changes", "Recent changes", false],
  ["/admin/merges", "Merged books", true],
  ["/admin/people", "People", false],
  ["/admin/api", "API usage", true],
  ["/admin/clicks", "Buy-link clicks", true],
] as const;
const links = computed(() => LINKS.filter(([, , run]) => !run || props.user.may_run));
// Sources carries the bar and isn't one of its pages: there the button says
// what it opens instead (Claude's choice of word).
const here = computed(() => links.value.find(([href]) => href === props.current)?.[1]);

const open = ref(false);
const button = ref<HTMLButtonElement | null>(null);
function close() {
  if (!open.value) return;
  open.value = false;
  button.value?.focus();
}
watch(
  () => props.current,
  () => (open.value = false),
);
</script>

<template>
  <Teleport to="#admin-bar" defer>
    <nav class="admin-bar admin-pages" aria-label="Admin" @keydown.esc="close">
      <div class="bar">
        <strong>Admin</strong>
        <!-- Only shown on a phone, where the links are folded under it. -->
        <button
          ref="button"
          type="button"
          class="bar-toggle"
          :aria-expanded="open"
          aria-controls="admin-pages"
          @click="open = !open"
        >
          <span v-if="here" class="visually-hidden">Admin pages; this is </span>{{ here ?? "Admin pages" }}
          <svg viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4" /></svg>
        </button>
        <div id="admin-pages" class="bar-links" :class="{ open }">
          <a
            v-for="[href, label] in links"
            :key="href"
            :href="href"
            :aria-current="href === current ? 'page' : undefined"
            >{{ label }}</a
          >
        </div>
      </div>
    </nav>
  </Teleport>
</template>

<style scoped>
/* On a wide screen the links are the bar's own, in its one wrapping row, and
   there's no button. */
.bar-links {
  display: contents;
}
.bar-toggle {
  display: none;
}
@media (max-width: 40rem) {
  /* Named through the nav so it outranks App.vue's rule for every admin
     bar, whichever of the two stylesheets comes first. */
  .admin-pages .bar {
    gap: 0 0.75rem;
    padding: 0.125rem 1rem;
  }
  .bar-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    min-width: 0;
    min-height: 2.75rem;
    padding: 0 0.875rem;
    border: 1px solid var(--admin-line);
    border-radius: var(--radius);
    background: none;
    color: var(--fg);
    font: inherit;
    font-weight: 700;
    text-align: left;
    cursor: pointer;
  }
  .bar-toggle:hover,
  .bar-toggle[aria-expanded="true"] {
    border-color: var(--fg);
  }
  .bar-toggle svg {
    flex: none;
    width: 0.625rem;
    height: 0.375rem;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.5;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .bar-toggle[aria-expanded="true"] svg {
    transform: rotate(180deg);
  }
  /* The rest, two to a row, each a row a thumb can hit. */
  .bar-links {
    display: none;
  }
  .bar-links.open {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    column-gap: 0.75rem;
    flex-basis: 100%;
    padding: 0.25rem 0 0.5rem;
  }
  .bar-links a {
    display: flex;
    align-items: center;
    min-height: 2.75rem;
  }
}
</style>
