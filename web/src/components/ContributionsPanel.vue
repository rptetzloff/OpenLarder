<script setup lang="ts">
import { onMounted, ref } from "vue";
import { type Group, REVIEW_LABELS, type Trust, myContributions, myTrust } from "../review";

// What you've added that's waiting for a moderator, or that they sent back
// with a reason to fix.
const groups = ref<Group[] | null>(null);
const trust = ref<Trust | null>(null);
const error = ref("");

onMounted(async () => {
  myTrust()
    .then((t) => (trust.value = t))
    .catch(() => {});
  try {
    groups.value = await myContributions();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
});
</script>

<template>
  <section class="tool-panel" aria-labelledby="contributions-title">
    <h2 id="contributions-title">Waiting for review</h2>
    <p v-if="trust?.trusted" class="status">
      You're a trusted contributor: what you add publishes at once, and moderators can still change
      or undo it.
    </p>
    <template v-else>
      <p class="muted">
        What you add is seen only by you and the moderators until one approves it. If one is sent
        back, fix it and it waits again.
      </p>
      <p v-if="trust && trust.trust !== 'withheld'" class="muted">
        Once {{ trust.needs_recipes.toLocaleString() }} of your recipes are approved, across
        {{ trust.needs_books }} books, what you add publishes without waiting: so far
        {{ trust.recipes.toLocaleString() }} recipes in {{ trust.books }}
        {{ trust.books === 1 ? "book" : "books" }}.
      </p>
    </template>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-else-if="!groups" class="status">Loading…</p>
    <ul v-else-if="groups.length" class="review-items">
      <li v-for="g in groups" :key="g.source.id">
        <div>
          <a :href="`/sources/${g.source.id}`">{{ g.source.title }}</a>
          <span v-if="g.source.review !== 'published'" class="muted">
            · {{ REVIEW_LABELS[g.source.review] }}</span
          >
          <p v-if="g.source.review === 'returned'" class="review-reason">
            “{{ g.source.review_note }}”
          </p>
          <ul v-if="g.recipes.length" class="review-recipes">
            <li v-for="r in g.recipes" :key="r.id">
              <a :href="`/recipes/${r.id}`">{{ r.title }}</a>
              <span class="muted"> · {{ REVIEW_LABELS[r.review] }}</span>
              <p v-if="r.review === 'returned'" class="review-reason">“{{ r.review_note }}”</p>
            </li>
          </ul>
        </div>
      </li>
    </ul>
    <p v-else class="status">Nothing of yours is waiting.</p>
  </section>
</template>
