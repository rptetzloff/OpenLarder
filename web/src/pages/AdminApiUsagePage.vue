<script setup lang="ts">
import { computed, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import type { Me } from "../me";
import { type Caller, type UsagePage, apiUsage, revokeAnyKey } from "../monitoring";

// Who outside the site uses the API, and how much: to see abuse.
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "API usage · Admin · OpenLarder";

const days = ref(7);
const page = ref<UsagePage | null>(null);
const error = ref("");
const allowed = computed(() => !!props.user?.is_admin);
const n = (v: number) => v.toLocaleString();
const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

async function load() {
  error.value = "";
  try {
    page.value = await apiUsage(days.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function revoke(c: Caller) {
  if (!c.key_id || !confirm(`Revoke “${c.key_name}”, ${c.owner}'s key? It stops working at once.`)) return;
  try {
    await revokeAnyKey(c.key_id);
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

watch(days, load);
watch(allowed, (yes) => yes && !page.value && load(), { immediate: true });
</script>

<template>
  <AdminBar v-if="user?.is_admin" current="/admin/api" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/admin">Admin</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">API usage</span>
    </nav>
    <div class="list-head">
      <h1>API usage</h1>
      <p class="muted">
        Programs reading the public API, busiest first; the site's own pages aren't counted. A
        caller without a key is a name made from its address, the same each day, and its network:
        the address itself isn't kept. Kept 30 days.
      </p>
    </div>
    <p v-if="!user?.is_admin" class="status">This is for admins.</p>
    <template v-else>
      <div class="kind-filter" role="group" aria-label="Over">
        <button
          v-for="d in [1, 7, 30]"
          :key="d"
          type="button"
          class="secondary small"
          :aria-pressed="days === d"
          @click="days = d"
        >
          {{ d === 1 ? "Today" : `${d} days` }}
        </button>
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-else-if="!page" class="status">Loading…</p>
      <template v-else>
        <p class="status">
          {{ n(page.requests) }} requests answered, {{ n(page.refused) }} refused over a limit,
          from {{ n(page.callers.length) }} {{ page.callers.length === 1 ? "caller" : "callers" }}.
        </p>
        <table v-if="page.callers.length" class="recipe-table usage-table">
          <thead>
            <tr>
              <th scope="col">Caller</th>
              <th scope="col" class="numeric">Today</th>
              <th scope="col" class="numeric">Requests</th>
              <th scope="col" class="numeric">Searches</th>
              <th scope="col" class="numeric">Refused</th>
              <th scope="col">Last seen</th>
              <th scope="col"><span class="visually-hidden">Revoke</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in page.callers" :key="c.caller">
              <td>
                <template v-if="c.key_name">
                  <strong>{{ c.key_name }}</strong>
                  <code v-if="c.key_prefix"> {{ c.key_prefix }}…</code>
                  <div v-if="c.owner" class="muted">{{ c.owner }}'s key</div>
                </template>
                <template v-else>
                  <strong>Address {{ c.caller.slice(3) }}</strong>
                  <div class="muted">{{ c.network ?? "network unknown" }}</div>
                </template>
              </td>
              <td class="numeric"><span class="cell-label">Today </span>{{ n(c.today) }}</td>
              <td class="numeric"><span class="cell-label">Requests </span>{{ n(c.requests) }}</td>
              <td class="numeric"><span class="cell-label">Searches </span>{{ n(c.searches) }}</td>
              <td class="numeric" :class="{ warn: c.refused }">
                <span class="cell-label">Refused </span>{{ n(c.refused) }}
              </td>
              <td><span class="cell-label">Last seen </span>{{ when(c.last_at) }}</td>
              <td>
                <button v-if="c.key_id" type="button" class="secondary small" @click="revoke(c)">
                  Revoke
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="status">No outside use in this time.</p>
      </template>
    </template>
  </article>
</template>
