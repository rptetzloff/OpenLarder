<script setup lang="ts">
// The yellow band under the header on admin pages and Sources: every admin
// page they may use, with the one you're on marked. Only rendered for a
// moderator or above; the administrators' pages only for them.
import { computed } from "vue";
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
  ["/admin/changes", "Recent changes", false],
  ["/admin/people", "People", false],
  ["/admin/api", "API usage", true],
  ["/admin/clicks", "Buy-link clicks", true],
] as const;
const links = computed(() => LINKS.filter(([, , run]) => !run || props.user.may_run));
</script>

<template>
  <Teleport to="#admin-bar" defer>
    <nav class="admin-bar" aria-label="Admin">
      <div class="bar">
        <strong>Admin</strong>
        <a
          v-for="[href, label] in links"
          :key="href"
          :href="href"
          :aria-current="href === current ? 'page' : undefined"
          >{{ label }}</a
        >
      </div>
    </nav>
  </Teleport>
</template>
