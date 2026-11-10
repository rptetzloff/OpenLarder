<script setup lang="ts">
import { computed, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import type { Me } from "../me";
import ProposalDiff from "../components/ProposalDiff.vue";
import {
  type Group,
  type Item,
  type Proposal,
  REVIEW_LABELS,
  approveAll,
  decide,
  decideProposal,
  openProposals,
  reviewQueue,
} from "../review";

// What contributors have added, waiting for a moderator. *Ray, 2026-11-10:*
// each item on its own, or all of a source's at once; one sent back keeps
// the reason, and comes back here once its contributor changes it.
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Review · Admin · OpenLarder";

const allowed = computed(() => !!props.user?.may_edit);
const groups = ref<Group[] | null>(null);
const proposals = ref<Proposal[]>([]);
const pending = ref(0);
const error = ref("");
const busy = ref(false);
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });

async function load() {
  error.value = "";
  try {
    const [queue, suggested] = await Promise.all([reviewQueue(), openProposals()]);
    proposals.value = suggested;
    groups.value = queue.groups;
    pending.value = queue.pending;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function act(work: () => Promise<unknown>) {
  busy.value = true;
  error.value = "";
  try {
    await work();
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

function sendBack(what: "sources" | "recipes", item: Item) {
  const note = prompt(`What needs fixing in “${item.title}”? The contributor reads this.`)?.trim();
  if (note) act(() => decide(what, item.id, "return", note));
}

function apply(p: Proposal) {
  if (p.changed_since && !confirm("It has changed since this was suggested. Apply it anyway, replacing that change?"))
    return;
  act(() => decideProposal(p.id, "apply", undefined, p.changed_since));
}

function declineProposal(p: Proposal) {
  const note = prompt(`Why not apply the change to “${p.title}”? The contributor reads this.`)?.trim();
  if (note) act(() => decideProposal(p.id, "decline", note));
}

const waitingIn = (g: Group) =>
  (g.source.review === "pending" ? 1 : 0) + g.recipes.filter((r) => r.review === "pending").length;

watch(allowed, (yes) => yes && !groups.value && load(), { immediate: true });
</script>

<template>
  <AdminBar v-if="user?.may_edit" :user="user" current="/admin/review" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/admin">Admin</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">Review</span>
    </nav>
    <div class="list-head">
      <h1>Review</h1>
      <p class="muted">
        Changes contributors have suggested to published recipes and sources, then the books and recipes they've
        added, oldest first. Until approved, only they and moderators see them. Send one back with
        what needs fixing, and it returns here once they've changed it.
      </p>
    </div>
    <p v-if="!user?.may_edit" class="status">This is for moderators.</p>
    <template v-else>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="!groups" class="status">Loading…</p>
      <p v-else-if="pending" class="status">{{ pending.toLocaleString() }} waiting.</p>
      <section v-if="groups && proposals.length" class="review-proposals" aria-labelledby="proposals-title">
        <h2 id="proposals-title">Suggested changes</h2>
        <article v-for="p in proposals" :key="p.id" class="review-group">
          <div class="review-head">
            <div>
              <h3>
                <a :href="p.href">{{ p.title }}</a>
                <span v-if="p.kind === 'recipe'" class="muted"> in {{ p.source_title }}</span>
                <span v-else class="muted"> (its details)</span>
              </h3>
              <p class="muted">Suggested by {{ p.by ?? "someone" }} on {{ day(p.created_at) }}</p>
              <p v-if="p.reason" class="review-reason">“{{ p.reason }}”</p>
              <p v-if="p.changed_since" class="error">
                It has changed since; applying this replaces that change.
              </p>
            </div>
            <div class="row-actions">
              <button type="button" class="primary small" :disabled="busy" @click="apply(p)">Apply</button>
              <button type="button" class="secondary small" :disabled="busy" @click="declineProposal(p)">
                Decline
              </button>
            </div>
          </div>
          <ProposalDiff :proposal="p" />
        </article>
      </section>
      <template v-if="groups?.length">
        <section v-for="g in groups" :key="g.source.id" class="review-group" :aria-labelledby="`rg-${g.source.id}`">
          <div class="review-head">
            <div>
              <h2 :id="`rg-${g.source.id}`">
                <a :href="`/sources/${g.source.id}`">{{ g.source.title }}</a>
              </h2>
              <p class="muted">
                <template v-if="g.source.review !== 'published'">
                  {{ REVIEW_LABELS[g.source.review] }} · added by {{ g.source.by ?? "someone" }} on
                  {{ day(g.source.created_at) }}
                </template>
                <template v-else>Published; recipes added to it are waiting.</template>
              </p>
              <p v-if="g.source.review === 'returned'" class="review-reason">
                “{{ g.source.review_note }}”
              </p>
            </div>
            <div class="row-actions">
              <button
                v-if="waitingIn(g) > 1"
                type="button"
                class="primary small"
                :disabled="busy"
                @click="act(() => approveAll(g.source.id))"
              >
                Approve all {{ waitingIn(g) }}
              </button>
              <template v-if="g.source.review === 'pending'">
                <button
                  type="button"
                  class="secondary small"
                  :disabled="busy"
                  @click="act(() => decide('sources', g.source.id, 'approve'))"
                >
                  Approve the {{ g.kind === "book" ? "book" : "source" }}
                </button>
                <button type="button" class="secondary small" :disabled="busy" @click="sendBack('sources', g.source)">
                  Send back
                </button>
              </template>
            </div>
          </div>
          <ul v-if="g.recipes.length" class="review-items">
            <li v-for="r in g.recipes" :key="r.id">
              <div>
                <a :href="`/recipes/${r.id}`">{{ r.title }}</a>
                <span class="muted">
                  · {{ REVIEW_LABELS[r.review] }} · {{ r.by ?? "someone" }}, {{ day(r.created_at) }}
                </span>
                <p v-if="r.review === 'returned'" class="review-reason">“{{ r.review_note }}”</p>
              </div>
              <div v-if="r.review === 'pending'" class="row-actions">
                <button
                  type="button"
                  class="secondary small"
                  :disabled="busy"
                  @click="act(() => decide('recipes', r.id, 'approve'))"
                >
                  Approve
                </button>
                <button type="button" class="secondary small" :disabled="busy" @click="sendBack('recipes', r)">
                  Send back
                </button>
              </div>
            </li>
          </ul>
        </section>
      </template>
      <p v-if="groups && !groups.length && !proposals.length" class="status">
        Nothing waiting for review.
      </p>
    </template>
  </article>
</template>
