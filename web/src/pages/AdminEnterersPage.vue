<script setup lang="ts">
import { computed, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import type { Me } from "../me";
import { type Person, findPeople, setEnterer } from "../requests";

// Who may claim book requests: a role admins grant. *Ray, 2026-11-09.*
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Enterers · Admin · OpenLarder";

const allowed = computed(() => !!props.user?.is_admin);
const q = ref("");
const people = ref<Person[] | null>(null);
const error = ref("");
const busy = ref(false);

async function load() {
  error.value = "";
  try {
    people.value = await findPeople(q.value.trim());
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function toggle(p: Person) {
  busy.value = true;
  error.value = "";
  try {
    const now = await setEnterer(p.id, !p.is_enterer);
    people.value = (people.value ?? []).map((x) => (x.id === p.id ? now : x));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

watch(allowed, (yes) => yes && !people.value && load(), { immediate: true });
</script>

<template>
  <AdminBar v-if="user?.is_admin" current="/admin/enterers" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/admin">Admin</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">Enterers</span>
    </nav>
    <div class="list-head">
      <h1>Enterers</h1>
      <p class="muted">
        Enterers claim <a href="/requests">requests</a> to queue them up. Admins can always claim.
        Find someone by name to make them one.
      </p>
    </div>
    <p v-if="!user?.is_admin" class="status">This is for admins.</p>
    <template v-else>
      <form class="inline-form" role="search" @submit.prevent="load">
        <label for="find-person" class="visually-hidden">Find someone by name</label>
        <input id="find-person" v-model="q" type="search" maxlength="100" placeholder="Find someone by name" />
        <button type="submit" class="primary">Find</button>
        <button v-if="q" type="button" class="secondary" @click="(q = ''), load()">Show enterers</button>
      </form>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="!people" class="status">Loading…</p>
      <table v-else-if="people.length" class="recipe-table">
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Role</th>
            <th scope="col" class="numeric">Claims</th>
            <th scope="col"><span class="visually-hidden">Change</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in people" :key="p.id">
            <td>{{ p.name ?? "No name yet" }}</td>
            <td>
              <span class="cell-label">Role </span>
              {{ [p.is_admin && "Admin", p.is_enterer && "Enterer"].filter(Boolean).join(", ") || "—" }}
            </td>
            <td class="numeric"><span class="cell-label">Claims </span>{{ p.claims }}</td>
            <td>
              <button type="button" class="secondary small" :disabled="busy" @click="toggle(p)">
                {{ p.is_enterer ? "Stop being an enterer" : "Make an enterer" }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="status">{{ q ? "No one by that name." : "No enterers yet." }}</p>
    </template>
  </article>
</template>
