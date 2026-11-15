<script setup lang="ts">
// The yellow band under the header on admin pages and Sources: every admin
// page they may use, with the one you're on marked. Only rendered for a
// moderator or above; the administrators' pages only for them.
//
// On a phone it is one row: "Admin" and a button naming the page you're on,
// which opens the rest. The band and its button are AdminBand.vue, which
// the bars that pages add for themselves use too.
import { computed } from "vue";
import type { Me } from "../me";
import AdminBand from "./AdminBand.vue";

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
  ["/admin/shops", "Shops", true],
] as const;
const links = computed(() => LINKS.filter(([, , run]) => !run || props.user.may_run));
// Sources carries the bar and isn't one of its pages: there the button says
// what it opens instead (Claude's choice of word).
const here = computed(() => links.value.find(([href]) => href === props.current)?.[1]);
</script>

<template>
  <AdminBand
    id="admin-pages"
    nav
    :label="here ?? 'Admin pages'"
    :before="here ? 'Admin pages; this is ' : undefined"
  >
    <a
      v-for="[href, label] in links"
      :key="href"
      :href="href"
      :aria-current="href === current ? 'page' : undefined"
      >{{ label }}</a
    >
  </AdminBand>
</template>
