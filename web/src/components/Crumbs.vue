<script setup lang="ts">
// A page's breadcrumb: where it sits, down to its parent and no further
// (Ray's round 5 list, item 4, 2026-11-15). The last crumb had been the
// page's own title, straight above the same words as its heading: two or
// three lines of a phone, more with a long book's name.
//
// On a phone only the parent shows, as one link back to it ("‹ Fiery
// Ferments"), on one line (App.vue: .crumbs). The trail in full, the page
// itself included, is still what search engines are given (pages.py: the
// BreadcrumbList).
defineProps<{
  // From the top to the page's parent, each a link.
  trail: { href: string; label: string }[];
}>();
</script>

<template>
  <nav class="crumbs" aria-label="Breadcrumb">
    <template v-for="(crumb, n) in trail" :key="crumb.href">
      <span v-if="n > 0" aria-hidden="true">/</span>
      <a :href="crumb.href" :class="{ 'crumb-back': n === trail.length - 1 }">{{ crumb.label }}</a>
    </template>
  </nav>
</template>
