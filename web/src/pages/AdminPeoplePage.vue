<script setup lang="ts">
import { computed, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import { type Me, type Role, ROLE_LABELS } from "../me";
import { type Person, findPeople, setRole, setTrust } from "../requests";

// People and their roles (roles.py). *Ray, 2026-11-10:* a moderator makes
// contributors, an administrator makes moderators, the owner makes
// administrators.
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "People · Admin · OpenLarder";

const allowed = computed(() => !!props.user?.may_edit);
const q = ref("");
const only = ref<Role | "">("");
const people = ref<Person[] | null>(null);
const error = ref("");
const busy = ref(false);
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
// Roles they may give, highest first, as the menu offers them.
const offered = computed(() => [...(props.user?.grants ?? [])].reverse());
const FILTERS: { role: Role | ""; label: string }[] = [
  { role: "", label: "Everyone with a role" },
  { role: "owner", label: "Owners" },
  { role: "admin", label: "Administrators" },
  { role: "moderator", label: "Moderators" },
  { role: "contributor", label: "Contributors" },
];

async function load() {
  error.value = "";
  try {
    people.value = await findPeople(q.value.trim(), only.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function change(p: Person, role: Role) {
  if (role === p.role) return;
  busy.value = true;
  error.value = "";
  try {
    const now = await setRole(p.id, role);
    people.value = (people.value ?? []).map((x) => (x.id === p.id ? now : x));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    await load();
  } finally {
    busy.value = false;
  }
}

const TRUST: Record<string, string> = {
  earned: "Trusted (earned)",
  granted: "Trusted",
  withheld: "Not trusted",
};
async function trustIt(p: Person, trust: "granted" | "withheld" | null) {
  busy.value = true;
  error.value = "";
  try {
    const now = await setTrust(p.id, trust);
    people.value = (people.value ?? []).map((x) => (x.id === p.id ? now : x));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

watch(only, () => {
  q.value = "";
  load();
});
watch(allowed, (yes) => yes && !people.value && load(), { immediate: true });
</script>

<template>
  <AdminBar v-if="user?.may_edit" :user="user" current="/admin/people" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/admin">Admin</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">People</span>
    </nav>
    <div class="list-head">
      <h1>People and roles</h1>
      <p class="muted">
        Contributors claim <a href="/requests">requests</a> to queue them up, and their additions
        wait for review until they're trusted: earned by enough approved recipes, or given here.
        Withholding it sticks; clearing it lets it be earned again. Moderators edit the
        catalog and work the flags and suggestions. Administrators also run imports and watch the
        API and buy links. You can give or take away only the roles below your own, and the owner
        is set outside the site.
      </p>
    </div>
    <p v-if="!user?.may_edit" class="status">This is for moderators.</p>
    <template v-else>
      <form class="inline-form" role="search" @submit.prevent="load">
        <label for="find-person" class="visually-hidden">Find someone by name</label>
        <input
          id="find-person"
          v-model="q"
          type="search"
          maxlength="100"
          placeholder="Find someone by name"
        />
        <button type="submit" class="primary">Find</button>
      </form>
      <div class="kind-filter" role="group" aria-label="Show">
        <button
          v-for="f in FILTERS"
          :key="f.role"
          type="button"
          class="secondary small"
          :aria-pressed="!q && only === f.role"
          @click="only === f.role ? ((q = ''), load()) : (only = f.role)"
        >
          {{ f.label }}
        </button>
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="!people" class="status">Loading…</p>
      <table v-else-if="people.length" class="recipe-table people-table">
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Role</th>
            <th scope="col">Trust</th>
            <th scope="col" class="numeric">Claims</th>
            <th scope="col">Joined</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in people" :key="p.id">
            <td>{{ p.name ?? "No name yet" }}<span v-if="p.id === user.id" class="muted"> (you)</span></td>
            <td>
              <span class="cell-label">Role </span>
              <template v-if="p.changeable">
                <label :for="`role-${p.id}`" class="visually-hidden">Role for {{ p.name }}</label>
                <select
                  :id="`role-${p.id}`"
                  :value="p.role"
                  :disabled="busy"
                  @change="change(p, ($event.target as HTMLSelectElement).value as Role)"
                >
                  <option v-for="r in offered" :key="r" :value="r">{{ ROLE_LABELS[r] }}</option>
                </select>
              </template>
              <template v-else>{{ ROLE_LABELS[p.role] }}</template>
            </td>
            <td>
              <span class="cell-label">Trust </span>
              <template v-if="p.role === 'contributor'">
                {{ p.trust ? TRUST[p.trust] : "Waits for review" }}
                <span v-if="p.id !== user.id" class="trust-actions">
                  <button
                    v-if="p.trust !== 'granted' && p.trust !== 'earned'"
                    type="button"
                    class="link"
                    :disabled="busy"
                    @click="trustIt(p, 'granted')"
                  >
                    Trust
                  </button>
                  <button
                    v-if="p.trust !== 'withheld'"
                    type="button"
                    class="link"
                    :disabled="busy"
                    @click="trustIt(p, 'withheld')"
                  >
                    Withhold
                  </button>
                  <button
                    v-if="p.trust"
                    type="button"
                    class="link"
                    :disabled="busy"
                    @click="trustIt(p, null)"
                  >
                    Clear
                  </button>
                </span>
              </template>
              <template v-else>—</template>
            </td>
            <td class="numeric"><span class="cell-label">Claims </span>{{ p.claims }}</td>
            <td><span class="cell-label">Joined </span>{{ day(p.created_at) }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="status">{{ q ? "No one by that name." : "No one here yet." }}</p>
    </template>
  </article>
</template>
