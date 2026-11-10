<script setup lang="ts">
import { computed, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
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
const allowed = computed(() => !!props.user?.may_edit);
const openTotal = computed(() =>
  Object.values(page.value?.open_by_kind ?? {}).reduce((a, b) => a + b, 0),
);
// The kinds worth a button: those with open suggestions, and the one chosen.
const kindChoices = computed(() =>
  Object.keys(KIND_LABELS).filter(
    (k) => (page.value?.open_by_kind[k] ?? 0) > 0 || k === kind.value || state.value !== "open",
  ),
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
  <AdminBar v-if="user?.may_edit" :user="user" current="/admin/suggestions" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/admin">Admin</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">Suggestions</span>
    </nav>
    <div class="list-head">
      <h1>Suggestions</h1>
      <p class="muted">
        A local model compared ingredients that look alike, and read recipes for the tags they
        could have, and suggests what to do. Accepting does it as if you'd done it by hand; a
        merged name stays as another name for the one kept, so lines written that way still find
        it. Those the model is certain of come first, then those it thinks likely, each with the
        closest pairs first.
      </p>
    </div>
    <p v-if="!user" class="status"><a href="/api/auth/login">Sign in</a> to see suggestions.</p>
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
            :aria-pressed="state === 'decided'"
            @click="state = 'decided'"
          >
            Decided
          </button>
        </div>
        <div v-if="kindChoices.length" class="kind-filter" role="group" aria-label="Kind">
          <button type="button" class="secondary small" :aria-pressed="!kind" @click="kind = ''">
            Any kind
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
      <p v-if="failed" role="alert">The suggestions couldn't be loaded. Try reloading the page.</p>
      <p v-else-if="!page" class="status">Loading…</p>
      <p v-else-if="items.length === 0" class="status">
        {{ state === "open" ? "No open suggestions." : "None decided yet." }}
      </p>
      <ul v-else class="suggestion-cards">
        <SuggestionItem v-for="s in items" :key="s.id" :suggestion="s" @decided="decided" />
      </ul>
      <button
        v-if="page && items.length < page.total"
        type="button"
        class="secondary show-more"
        :disabled="loading"
        @click="load(true)"
      >
        Show more ({{ (page.total - items.length).toLocaleString() }} left)
      </button>
    </template>
  </article>
</template>
