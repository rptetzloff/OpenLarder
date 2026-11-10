<script setup lang="ts">
import type { Review } from "../review";

// On a source's or recipe's page, for its maker and moderators: it's
// waiting for review, or was sent back with the moderator's reason.
defineProps<{ review: Review; note: string | null; what: string }>();
</script>

<template>
  <div v-if="review !== 'published'" class="review-notice" :class="review" role="status">
    <p v-if="review === 'pending'">
      <strong>Waiting for review.</strong> Only you and the moderators see this {{ what }} until a
      moderator approves it.
    </p>
    <template v-else>
      <p>
        <strong>Sent back.</strong> A moderator asked for a change before this {{ what }} goes
        public. Change it and it goes back to waiting.
      </p>
      <p v-if="note" class="review-reason">“{{ note }}”</p>
    </template>
  </div>
</template>
