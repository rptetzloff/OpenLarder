<script setup lang="ts">
import { onMounted, ref } from "vue";
import { type Proposal, myProposals, withdrawProposal } from "../review";

// The changes you've suggested to published recipes, and what became of them.
const proposals = ref<Proposal[] | null>(null);
const error = ref("");
const STATES: Record<Proposal["status"], string> = {
  open: "Waiting for a moderator",
  applied: "Applied",
  declined: "Declined",
  withdrawn: "Withdrawn",
};

async function load() {
  try {
    proposals.value = await myProposals();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

async function withdraw(p: Proposal) {
  if (!confirm(`Withdraw your suggestion for “${p.recipe_title}”?`)) return;
  try {
    await withdrawProposal(p.id);
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

onMounted(load);
</script>

<template>
  <section class="tool-panel" aria-labelledby="proposals-mine-title">
    <h2 id="proposals-mine-title">Suggested changes</h2>
    <p class="muted">
      Changes you've suggested to published recipes. A moderator applies them or says why not.
    </p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-else-if="!proposals" class="status">Loading…</p>
    <ul v-else-if="proposals.length" class="review-items">
      <li v-for="p in proposals" :key="p.id">
        <div>
          <a :href="`/recipes/${p.recipe_id}`">{{ p.recipe_title }}</a>
          <span class="muted"> · {{ STATES[p.status] }}</span>
          <p v-if="p.status === 'declined' && p.note" class="review-reason">“{{ p.note }}”</p>
        </div>
        <button v-if="p.status === 'open'" type="button" class="secondary small" @click="withdraw(p)">
          Withdraw
        </button>
      </li>
    </ul>
    <p v-else class="status">You haven't suggested any changes yet.</p>
  </section>
</template>
