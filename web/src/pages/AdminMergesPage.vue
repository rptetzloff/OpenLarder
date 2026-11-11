<script setup lang="ts">
import { ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import type { Me } from "../me";

// Every merge of two books, and taking one apart again: for
// administrators, as a check on moderators. *Ray, 2026-11-11.*
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Merged books · Admin · OpenLarder";

interface Book {
  id: string;
  title: string;
}

interface Merge {
  id: string;
  gone: Book;
  kept: Book | null;
  editions: number;
  recipes: number;
  merged_by: string | null;
  merged_at: string;
  undone_by: string | null;
  undone_at: string | null;
}

const merges = ref<Merge[] | null>(null);
const failed = ref(false);
const busy = ref("");
const errors = ref<Record<string, string>>({});
const when = (iso: string) => new Date(iso).toLocaleString();
const many = (n: number, one: string, more: string) => `${n.toLocaleString()} ${n === 1 ? one : more}`;

async function load() {
  try {
    const res = await fetch("/api/merges");
    if (!res.ok) throw new Error();
    merges.value = await res.json();
  } catch {
    failed.value = true;
  }
}

async function unmerge(m: Merge) {
  const into = m.kept ? `“${m.kept.title}”` : "the book it went into";
  if (
    !confirm(
      `Unmerge “${m.gone.title}”? It comes back as its own book, and what it brought to ${into} goes back with it.`,
    )
  )
    return;
  busy.value = m.id;
  errors.value = {};
  try {
    const res = await fetch(`/api/merges/${m.id}/unmerge`, { method: "POST" });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
    await load();
  } catch (e) {
    errors.value = { [m.id]: e instanceof Error ? e.message : String(e) };
  } finally {
    busy.value = "";
  }
}

watch(
  () => !!props.user?.may_run,
  (yes) => yes && merges.value === null && load(),
  { immediate: true },
);
</script>

<template>
  <AdminBar v-if="user?.may_edit" :user="user" current="/admin/merges" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/admin">Admin</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">Merged books</span>
    </nav>
    <div class="list-head">
      <h1>Merged books</h1>
      <p class="muted">
        Every merge of two books, newest first, by whom. Unmerging puts the book removed back as it
        was, with whatever it brought that's still with the other; anything added since stays where
        it is.
      </p>
    </div>
    <p v-if="!user?.may_run" class="status">This is for administrators.</p>
    <p v-else-if="failed" role="alert">The merges couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="merges === null" class="status">Loading…</p>
    <p v-else-if="merges.length === 0" class="status">
      No books merged yet. Merges made before this list existed aren't in it.
    </p>
    <table v-else class="recipe-table merge-table">
      <thead>
        <tr>
          <th scope="col">Merged</th>
          <th scope="col">Book removed</th>
          <th scope="col">Into</th>
          <th scope="col">Unmerge</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="m in merges" :key="m.id">
          <td>
            <span class="strong">{{ when(m.merged_at) }}</span>
            <div class="muted">{{ m.merged_by ?? "Someone since removed" }}</div>
          </td>
          <td>
            <span class="cell-label">Removed: </span>
            <a v-if="m.undone_at" :href="`/sources/${m.gone.id}`">{{ m.gone.title }}</a>
            <template v-else>{{ m.gone.title }}</template>
            <div class="muted">
              {{ many(m.editions, "edition", "editions") }}, {{ many(m.recipes, "recipe", "recipes") }}
            </div>
          </td>
          <td>
            <span class="cell-label">Into: </span>
            <a v-if="m.kept" :href="`/sources/${m.kept.id}`">{{ m.kept.title }}</a>
            <span v-else class="muted">A book since removed</span>
          </td>
          <td>
            <template v-if="m.undone_at">
              Unmerged {{ when(m.undone_at) }}
              <div class="muted">{{ m.undone_by ?? "Someone since removed" }}</div>
            </template>
            <template v-else>
              <button
                type="button"
                class="secondary"
                :disabled="busy !== ''"
                :aria-label="`Unmerge ${m.gone.title}`"
                @click="unmerge(m)"
              >
                {{ busy === m.id ? "Unmerging…" : "Unmerge" }}
              </button>
              <p v-if="errors[m.id]" class="error" role="alert">{{ errors[m.id] }}</p>
            </template>
          </td>
        </tr>
      </tbody>
    </table>
  </article>
</template>
