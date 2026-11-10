<script setup lang="ts">
import { computed, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import FlagRow from "../components/FlagRow.vue";
import { type Flag, type FlagPage, KIND_LABELS, fetchFlags } from "../flags";
import type { Me } from "../me";

// Every flag for an admin (scope "all"), or the flags on your own recipes.
const props = defineProps<{ user: Me | null | undefined; scope: "all" | "mine" }>();
const heading = props.scope === "all" ? "Flagged recipes" : "My flagged recipes";
document.title = `${heading} · OpenLarder`;

const state = ref<"open" | "dealt_with">("open");
const kind = ref("");
const page = ref<FlagPage | null>(null);
const flags = ref<Flag[]>([]);
const failed = ref(false);
const loading = ref(false);
const allowed = computed(() => (props.scope === "all" ? !!props.user?.may_edit : !!props.user));
const openTotal = computed(() =>
  Object.values(page.value?.open_by_kind ?? {}).reduce((a, b) => a + b, 0),
);
// The kinds worth a button: those with open flags, and the one chosen.
const kindChoices = computed(() =>
  Object.keys(KIND_LABELS).filter(
    (k) => (page.value?.open_by_kind[k] ?? 0) > 0 || k === kind.value || state.value !== "open",
  ),
);

async function load(more = false) {
  loading.value = true;
  failed.value = false;
  try {
    const next = await fetchFlags({
      scope: props.scope,
      state: state.value,
      kind: kind.value || undefined,
      offset: more ? flags.value.length : 0,
    });
    page.value = next;
    flags.value = more ? [...flags.value, ...next.flags] : next.flags;
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

function resolved(updated: Flag) {
  // Stays in place, marked, until the next load; the counts follow now.
  flags.value = flags.value.map((f) => (f.id === updated.id ? updated : f));
  if (page.value && page.value.open_by_kind[updated.kind]) page.value.open_by_kind[updated.kind]--;
}

watch([state, kind], () => load());
// Who's signed in arrives after the page mounts, so load once it says yes.
watch(allowed, (yes) => {
  if (yes && !page.value) load();
}, { immediate: true });
</script>

<template>
  <AdminBar v-if="scope === 'all' && user?.may_edit" :user="user" current="/admin/flags" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a v-if="scope === 'all'" href="/admin">Admin</a>
      <a v-else href="/account">Your account</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">{{ heading }}</span>
    </nav>
    <div class="list-head">
      <h1>{{ heading }}</h1>
      <p class="muted">
        A flag means something about a recipe looked wrong when it was entered or imported. Fix the
        recipe and mark the flag fixed, or dismiss it if it's wrong.
      </p>
    </div>
    <p v-if="!user" class="status"><a href="/api/auth/login">Sign in</a> to see flags.</p>
    <p v-else-if="!allowed" class="status">This is for moderators.</p>
    <template v-else>
      <div class="list-filters">
        <div class="kind-filter" role="group" aria-label="Show">
          <button type="button" class="secondary small" :aria-pressed="state === 'open'" @click="state = 'open'">
            Open <span class="count">{{ openTotal.toLocaleString() }}</span>
          </button>
          <button
            type="button"
            class="secondary small"
            :aria-pressed="state === 'dealt_with'"
            @click="state = 'dealt_with'"
          >
            Dealt with
          </button>
        </div>
        <div v-if="kindChoices.length" class="kind-filter" role="group" aria-label="Reason">
          <button type="button" class="secondary small" :aria-pressed="!kind" @click="kind = ''">
            Any reason
          </button>
          <button
            v-for="k in kindChoices"
            :key="k"
            type="button"
            class="secondary small"
            :aria-pressed="kind === k"
            @click="kind = kind === k ? '' : k"
          >
            {{ KIND_LABELS[k] }}
            <span v-if="state === 'open'" class="count">
              {{ (page?.open_by_kind[k] ?? 0).toLocaleString() }}
            </span>
          </button>
        </div>
      </div>
      <p v-if="failed" role="alert">The flags couldn't be loaded. Try reloading the page.</p>
      <p v-else-if="!page" class="status">Loading…</p>
      <p v-else-if="flags.length === 0" class="status">
        {{ state === "open" ? "No open flags." : "None dealt with yet." }}
      </p>
      <table v-else class="recipe-table flag-table">
        <thead>
          <tr>
            <th scope="col">Recipe</th>
            <th scope="col">Why it's flagged</th>
            <th scope="col">{{ state === "open" ? "Deal with it" : "Outcome" }}</th>
          </tr>
        </thead>
        <tbody>
          <FlagRow v-for="f in flags" :key="f.id" :flag="f" @resolved="resolved" />
        </tbody>
      </table>
      <button
        v-if="page && flags.length < page.total"
        type="button"
        class="secondary show-more"
        :disabled="loading"
        @click="load(true)"
      >
        Show more ({{ (page.total - flags.length).toLocaleString() }} left)
      </button>
    </template>
  </article>
</template>
