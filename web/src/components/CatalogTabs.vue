<script setup lang="ts">
// Ingredients and Equipment, the two lists of what a recipe takes, as a
// pair of tabs over each (Ray's equipment spec, 2026-11-15), beside the
// header's own link to each. They are links to two pages, so a nav with
// the page it's on marked, not a tablist.
defineProps<{ here: "ingredients" | "equipment" }>();
</script>

<template>
  <nav class="catalog-tabs" aria-label="Ingredients and equipment">
    <a href="/ingredients" :aria-current="here === 'ingredients' ? 'page' : undefined"
      >Ingredients</a
    >
    <a href="/equipment" :aria-current="here === 'equipment' ? 'page' : undefined">Equipment</a>
  </nav>
</template>

<style scoped>
.catalog-tabs {
  display: flex;
  gap: 0 0.25rem;
  margin-bottom: 1.25rem;
  border-bottom: 1px solid var(--line);
}
/* 44px to tap at any width: 20px of line and 12px above and below. */
.catalog-tabs a {
  padding: 0.75rem 0.75rem calc(0.75rem - 3px);
  border-bottom: 3px solid transparent;
  color: var(--muted);
  font-size: 0.9375rem;
  line-height: 1.25rem;
  text-decoration: none;
}
.catalog-tabs a:hover {
  color: var(--fg);
}
.catalog-tabs a[aria-current="page"] {
  border-bottom-color: var(--accent);
  color: var(--fg);
  font-weight: 700;
}
</style>
