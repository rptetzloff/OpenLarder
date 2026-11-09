<script setup lang="ts">
import { computed, ref, watch } from "vue";
import SuggestionItem from "../components/SuggestionItem.vue";
import { KIND_LABELS, type Suggestion, type SuggestionPage, fetchSuggestions } from "../suggestions";
import type { Me } from "../me";

// What local models suggest, for an admin to accept or dismiss.
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Suggestions · OpenLarder";

const state = ref<"open" | "decided">("open");
const kind = ref("");
const page = ref<SuggestionPage | null>(null);
const items = ref<Suggestion[]>([]);
const failed = ref(false);
const loading = ref(false);
const allowed = computed(() => !!props.user?.is_admin);
const openTotal = computed(() =>
  Object.values(page.value?.open_by_kind ?? {}).reduce((a, b) => a + b, 0),
);

async function load(more = false) {
  loading.value = true;
  failed.value = false;
  try {
    const next = await fetchSuggestions({
      state: state.value,
      kind: kind.value || undefined,
      offset: more ? items.value.length : 0,
    });
    page.value = next;
    items.value = more ? [...items.value, ...next.suggestions] : next.suggestions;
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
}

function decided(updated: Suggestion) {
  // Stays in place, marked, until the next load; the counts follow now.
  items.value = items.value.map((s) => (s.id === updated.id ? updated : s));
  if (page.value?.open_by_kind[updated.kind]) page.value.open_by_kind[updated.kind]--;
}

watch([state, kind], () => load());
// Who's signed in arrives after the page mounts, so load once it says yes.
watch(allowed, (yes) => {
  if (yes && !page.value) load();
}, { immediate: true });
</script>

<template>
  <article>
    <p><a href="/admin">← Admin</a></p>
    <h1>Suggestions</h1>
    <p v-if="!user" class="status"><a href="/api/auth/login">Sign in</a> to see suggestions.</p>
    <p v-else-if="!allowed" class="status">This is for admins.</p>
    <template v-else>
      <p class="status">
        A local model compared ingredients that look alike and suggests what to do with them.
        Accepting does it as if you'd done it on the ingredient's page; a merged name stays as
        another name for the one kept, so lines written that way still find it. The closest pairs
        come first.
      </p>
      <div class="flag-filters">
        <label>
          Show
          <select v-model="state">
            <option value="open">Open ({{ openTotal.toLocaleString() }})</option>
            <option value="decided">Decided</option>
          </select>
        </label>
        <label>
          Kind
          <select v-model="kind">
            <option value="">Any</option>
            <option v-for="(label, k) in KIND_LABELS" :key="k" :value="k">
              {{ label }}{{ state === "open" ? ` (${(page?.open_by_kind[k] ?? 0).toLocaleString()})` : "" }}
            </option>
          </select>
        </label>
      </div>
      <p v-if="failed" role="alert">The suggestions couldn't be loaded. Try reloading the page.</p>
      <p v-else-if="!page" class="status">Loading…</p>
      <p v-else-if="items.length === 0" class="status">
        {{ state === "open" ? "No open suggestions." : "None decided yet." }}
      </p>
      <ul v-else class="flag-list">
        <SuggestionItem v-for="s in items" :key="s.id" :suggestion="s" @decided="decided" />
      </ul>
      <button
        v-if="page && items.length < page.total"
        type="button"
        class="primary"
        :disabled="loading"
        @click="load(true)"
      >
        Show more ({{ (page.total - items.length).toLocaleString() }} left)
      </button>
    </template>
  </article>
</template>
