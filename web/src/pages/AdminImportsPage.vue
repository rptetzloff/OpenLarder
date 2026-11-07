<script setup lang="ts">
import { onMounted, ref } from "vue";
import type { Me } from "../me";

defineProps<{ user: Me | null | undefined }>();
document.title = "Import history · Admin · OpenLarder";

interface Run {
  id: string;
  started_by: string | null;
  started_at: string;
  finished_at: string | null;
  books_in_list: number;
  recipes_in_file: number;
  books_added: number;
  books_existing: number;
  books_failed: number;
  recipes_created: number;
  recipes_skipped: number;
  recipes_not_imported: number;
  flags_raised: number;
  lines: number;
}

const runs = ref<Run[] | null>(null);
const failed = ref(false);
const n = (v: number) => v.toLocaleString();
const when = (iso: string) => new Date(iso).toLocaleString();

onMounted(async () => {
  try {
    const res = await fetch("/api/import/runs");
    if (!res.ok) throw new Error();
    runs.value = await res.json();
  } catch {
    failed.value = true;
  }
});
</script>

<template>
  <article>
    <p><a href="/admin">← Admin</a></p>
    <h1>Import history</h1>
    <p v-if="!user?.is_admin" class="status">This is for admins.</p>
    <p v-else-if="failed" role="alert">The history couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="runs === null" class="status">Loading…</p>
    <p v-else-if="runs.length === 0">No imports yet. Runs before the history existed aren't listed.</p>
    <ul v-else class="run-list">
      <li v-for="run in runs" :key="run.id">
        <strong>{{ when(run.started_at) }}</strong>
        <span v-if="run.started_by"> · {{ run.started_by }}</span>
        <span v-if="!run.finished_at" class="error"> · didn't finish</span>
        <ul>
          <li>
            Books: {{ n(run.books_in_list) }} in the list, {{ n(run.books_added) }} added,
            {{ n(run.books_existing) }} already here<template v-if="run.books_failed">, {{ n(run.books_failed) }} not added</template>.
          </li>
          <li>
            Recipes: {{ n(run.recipes_in_file) }} in the file, {{ n(run.recipes_created) }} added,
            {{ n(run.recipes_skipped) }} already there, {{ n(run.recipes_not_imported) }} not imported.
          </li>
          <li>{{ n(run.flags_raised) }} flags raised.</li>
        </ul>
        <a v-if="run.lines" :href="`/api/import/runs/${run.id}/report.csv`">Download the report ({{ n(run.lines) }} lines)</a>
        <span v-else class="status">Nothing to report.</span>
      </li>
    </ul>
  </article>
</template>
