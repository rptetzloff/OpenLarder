<script setup lang="ts">
// The yellow band under the header on admin pages and Sources: every admin
// page, with the one you're on marked. Only rendered for an admin.
defineProps<{ current?: string }>();

const LINKS = [
  ["/admin", "Overview"],
  ["/admin/import", "Bulk import"],
  ["/admin/imports", "Import history"],
  ["/admin/flags", "Flagged recipes"],
  ["/admin/suggestions", "Suggestions"],
  ["/admin/api", "API usage"],
  ["/admin/clicks", "Buy-link clicks"],
] as const;
</script>

<template>
  <Teleport to="#admin-bar" defer>
    <nav class="admin-bar" aria-label="Admin">
      <div class="bar">
        <strong>Admin</strong>
        <a
          v-for="[href, label] in LINKS"
          :key="href"
          :href="href"
          :aria-current="href === current ? 'page' : undefined"
          >{{ label }}</a
        >
      </div>
    </nav>
  </Teleport>
</template>
