<script setup lang="ts">
import { computed, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import type { Me } from "../me";
import { REASONS, type Report, decideReport, reportQueue } from "../reports";

// Problems people have reported with public records, oldest first, for
// moderators to fix or dismiss. *Ray, 2026-11-10.*
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Reports · Admin · OpenLarder";

const STATES = [
  { state: "open", label: "Open" },
  { state: "resolved", label: "Fixed" },
  { state: "dismissed", label: "Dismissed" },
] as const;
const state = ref<"open" | "resolved" | "dismissed">("open");
const reports = ref<Report[] | null>(null);
const counts = ref<Record<string, number>>({});
const error = ref("");
const busy = ref(false);
const allowed = computed(() => !!props.user?.may_edit);
const reasonLabel = (r: string) => REASONS.find((x) => x.reason === r)?.label ?? r;
const when = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });

async function load() {
  error.value = "";
  try {
    const page = await reportQueue(state.value);
    reports.value = page.reports;
    counts.value = page.counts;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function decide(r: Report, action: "resolve" | "dismiss") {
  const asked =
    action === "resolve" ? "What did you change? (optional)" : "Why is it dismissed? (optional)";
  const note = prompt(asked);
  if (note === null) return;
  busy.value = true;
  try {
    await decideReport(r.id, action, note.trim());
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

watch(state, load);
watch(allowed, (yes) => yes && !reports.value && load(), { immediate: true });
</script>

<template>
  <AdminBar v-if="user?.may_edit" :user="user" current="/admin/reports" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/admin">Admin</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">Reports</span>
    </nav>
    <div class="list-head">
      <h1>Reports</h1>
      <p class="muted">
        Problems people have reported with recipes, sources, ingredients and authors, oldest
        first. Fix what's wrong on the record's page, then mark the report fixed; or dismiss it.
        Someone signed out is shown as no one.
      </p>
    </div>
    <p v-if="!user?.may_edit" class="status">This is for moderators.</p>
    <template v-else>
      <div class="kind-filter" role="group" aria-label="Show">
        <button
          v-for="s in STATES"
          :key="s.state"
          type="button"
          class="secondary small"
          :aria-pressed="state === s.state"
          @click="state = s.state"
        >
          {{ s.label }}<span class="count">{{ counts[s.state] ?? 0 }}</span>
        </button>
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="!reports" class="status">Loading…</p>
      <ul v-else-if="reports.length" class="review-items report-list">
        <li v-for="r in reports" :key="r.id">
          <div>
            <a v-if="r.href" :href="r.href">{{ r.title }}</a>
            <span v-else class="muted">A {{ r.kind }} that's gone, or isn't yours to see</span>
            <span class="muted"> · {{ r.kind }} · {{ when(r.created_at) }}</span>
            <p class="report-reason">
              <strong>{{ reasonLabel(r.reason) }}</strong>
              <template v-if="r.by"> · from {{ r.by }}</template>
              <template v-if="r.others">
                · {{ r.others }} other open {{ r.others === 1 ? "report" : "reports" }} of it
              </template>
            </p>
            <p v-if="r.note" class="review-reason">“{{ r.note }}”</p>
            <p v-if="r.resolution" class="muted">{{ r.resolution }}</p>
          </div>
          <div v-if="r.status === 'open'" class="row-actions">
            <button type="button" class="primary small" :disabled="busy" @click="decide(r, 'resolve')">
              Fixed
            </button>
            <button type="button" class="secondary small" :disabled="busy" @click="decide(r, 'dismiss')">
              Dismiss
            </button>
          </div>
        </li>
      </ul>
      <p v-else class="status">{{ state === "open" ? "Nothing reported." : "None." }}</p>
    </template>
  </article>
</template>
