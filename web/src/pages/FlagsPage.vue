<script setup lang="ts">
import { computed, ref, watch } from "vue";
import FlagItem from "../components/FlagItem.vue";
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
const allowed = computed(() => (props.scope === "all" ? !!props.user?.is_admin : !!props.user));
const openTotal = computed(() =>
  Object.values(page.value?.open_by_kind ?? {}).reduce((a, b) => a + b, 0),
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
  // Out of the open list once dealt with; the counts refresh on next load.
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
  <article>
    <p v-if="scope === 'all'"><a href="/admin">← Admin</a></p>
    <p v-else><a href="/account">← Your account</a></p>
    <h1>{{ heading }}</h1>
    <p v-if="!user" class="status"><a href="/api/auth/login">Sign in</a> to see flags.</p>
    <p v-else-if="!allowed" class="status">This is for admins.</p>
    <template v-else>
      <p class="status">
        A flag means something about a recipe looked wrong when it was entered or imported. Fix the
        recipe and mark the flag fixed, or dismiss it if it's wrong.
      </p>
      <div class="flag-filters">
        <label>
          Show
          <select v-model="state">
            <option value="open">Open ({{ openTotal.toLocaleString() }})</option>
            <option value="dealt_with">Dealt with</option>
          </select>
        </label>
        <label>
          Reason
          <select v-model="kind">
            <option value="">Any</option>
            <option v-for="(label, k) in KIND_LABELS" :key="k" :value="k">
              {{ label }}{{ state === "open" ? ` (${(page?.open_by_kind[k] ?? 0).toLocaleString()})` : "" }}
            </option>
          </select>
        </label>
      </div>
      <p v-if="failed" role="alert">The flags couldn't be loaded. Try reloading the page.</p>
      <p v-else-if="!page" class="status">Loading…</p>
      <p v-else-if="flags.length === 0" class="status">
        {{ state === "open" ? "No open flags." : "None dealt with yet." }}
      </p>
      <ul v-else class="flag-list">
        <FlagItem v-for="f in flags" :key="f.id" :flag="f" :show-recipe="true" @resolved="resolved" />
      </ul>
      <button
        v-if="page && flags.length < page.total"
        type="button"
        class="primary"
        :disabled="loading"
        @click="load(true)"
      >
        Show more ({{ (page.total - flags.length).toLocaleString() }} left)
      </button>
    </template>
  </article>
</template>
