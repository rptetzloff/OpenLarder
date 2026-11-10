<script setup lang="ts">
import { onMounted, ref } from "vue";
import AdminBar from "../components/AdminBar.vue";
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
  <AdminBar v-if="user?.may_edit" :user="user" current="/admin/imports" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/admin">Admin</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">Import history</span>
    </nav>
    <div class="list-head">
      <h1>Import history</h1>
      <p class="muted">Every bulk import, newest first, with what it added and its report.</p>
    </div>
    <p v-if="!user?.may_run" class="status">This is for administrators.</p>
    <p v-else-if="failed" role="alert">The history couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="runs === null" class="status">Loading…</p>
    <p v-else-if="runs.length === 0" class="status">
      No imports yet. Runs before the history existed aren't listed.
      <a href="/admin/import">Start an import</a>
    </p>
    <table v-else class="recipe-table import-table">
      <thead>
        <tr>
          <th scope="col">Started</th>
          <th scope="col">Books</th>
          <th scope="col">Recipes</th>
          <th scope="col" class="numeric">Flags</th>
          <th scope="col">Report</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="run in runs" :key="run.id">
          <td>
            <span class="strong">{{ when(run.started_at) }}</span>
            <div v-if="run.started_by" class="muted">{{ run.started_by }}</div>
            <div v-if="!run.finished_at" class="error">Didn't finish</div>
          </td>
          <td>
            <span class="cell-label">Books: </span>{{ n(run.books_added) }} added of
            {{ n(run.books_in_list) }}
            <div class="muted">
              {{ n(run.books_existing) }} already here<template v-if="run.books_failed"
                >, {{ n(run.books_failed) }} not added</template
              >
            </div>
          </td>
          <td>
            <span class="cell-label">Recipes: </span>{{ n(run.recipes_created) }} added of
            {{ n(run.recipes_in_file) }}
            <div class="muted">
              {{ n(run.recipes_skipped) }} already there, {{ n(run.recipes_not_imported) }} not
              imported
            </div>
          </td>
          <td class="numeric">
            {{ n(run.flags_raised) }}<span class="cell-label"> flags raised</span>
          </td>
          <td>
            <a v-if="run.lines" :href="`/api/import/runs/${run.id}/report.csv`"
              >Download ({{ n(run.lines) }} lines)</a
            >
            <span v-else class="muted">Nothing to report</span>
          </td>
        </tr>
      </tbody>
    </table>
  </article>
</template>
