<script setup lang="ts">
// The yellow band under the header: "Admin" and the links given to it. The
// admin pages' bar is one (AdminBar.vue), and so are the bars an
// ingredient's, a source's and an author's page add for themselves.
//
// On a phone it is one row: "Admin" and a button, which opens the links.
// Ray's round 4 list, B1, 2026-11-14, for the admin pages: their thirteen
// links wrapped onto five rows, 157px of every admin page at 384px wide.
// His round 5 list, item 5, 2026-11-15, for the pages' own, "using the same
// component as the main bar": an ingredient's was 99px there, three rows,
// and a source's and an author's 70px, two.
import { ref } from "vue";

defineProps<{
  // The button's words on a phone: the page you're on, or the thing the
  // links are for ("This ingredient").
  label: string;
  // Said before them to a screen reader, which may come to the button
  // without the "Admin" beside it.
  before?: string;
  // The links' id, for aria-controls.
  id: string;
  // The links are pages to go to, so the band is a navigation landmark. A
  // page's own are mostly places further down it, and it isn't.
  nav?: boolean;
}>();

const open = ref(false);
const button = ref<HTMLButtonElement | null>(null);
function close() {
  if (!open.value) return;
  open.value = false;
  button.value?.focus();
}
// A link that was followed shuts the links: one to a place on this page
// leaves the band where it is, open over what was asked for. Focus isn't
// given back to the button, since it has gone where the link led.
function followed(event: MouseEvent) {
  if ((event.target as Element).closest("a")) open.value = false;
}
</script>

<template>
  <Teleport to="#admin-bar" defer>
    <component
      :is="nav ? 'nav' : 'div'"
      class="admin-bar admin-band"
      :aria-label="nav ? 'Admin' : undefined"
      @keydown.esc="close"
    >
      <div class="bar">
        <strong>Admin</strong>
        <!-- Only shown on a phone, where the links are folded under it. -->
        <button
          ref="button"
          type="button"
          class="bar-toggle"
          :aria-expanded="open"
          :aria-controls="id"
          @click="open = !open"
        >
          <span v-if="before" class="visually-hidden">{{ before }}</span
          >{{ label }}
          <svg viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4" /></svg>
        </button>
        <div :id="id" class="bar-links" :class="{ open }" @click="followed">
          <slot />
        </div>
      </div>
    </component>
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
  /* Named through the band so it outranks App.vue's rule for every admin
     bar, whichever of the two stylesheets comes first. */
  .admin-band .bar {
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
  .bar-links :deep(a) {
    display: flex;
    align-items: center;
    min-height: 2.75rem;
  }
  /* What isn't a link is a sentence, with links in it or none ("Possible
     duplicate: Ann Author · Merge"; "Delete (only when nothing uses it)"):
     a row of its own, its parts side by side. */
  .bar-links > :deep(span) {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0 0.375rem;
    grid-column: 1 / -1;
    min-height: 2.75rem;
  }
}
</style>
