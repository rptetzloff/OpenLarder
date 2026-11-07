<script setup lang="ts">
import type { Me } from "../me";

defineProps<{ user: Me | null | undefined }>();
document.title = "Admin · OpenLarder";
</script>

<template>
  <article>
    <h1>Admin</h1>
    <p v-if="!user?.is_admin" class="status">This is for admins.</p>
    <ul v-else>
      <li><a href="/admin/import">Import</a>: add books and recipes from a book list and a recipe list.</li>
      <li><a href="/admin/imports">Import history</a>: every import, with its totals and report.</li>
    </ul>
  </article>
</template>
