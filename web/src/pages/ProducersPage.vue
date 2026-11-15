<script setup lang="ts">
// Producers (Ray's round 4 list, part D4, 2026-11-13): farms, mills and
// makers that sell ingredients themselves. One card each, in the order an
// administrator put them in; where each ships is said, and nobody's place
// is guessed.
import { onMounted, ref } from "vue";
import ProducerCard from "../components/ProducerCard.vue";
import { type Producer, listProducers } from "../producers";

document.title = "Producers · OpenLarder";
const producers = ref<Producer[] | null>(null);
const failed = ref(false);

onMounted(async () => {
  try {
    producers.value = await listProducers();
  } catch {
    failed.value = true;
  }
});
</script>

<template>
  <article class="wide">
    <div class="list-head">
      <h1>Producers</h1>
      <p class="muted">
        Farms, mills and makers that sell ingredients themselves. What following a link earns, and
        for whom, is said beside it.
      </p>
    </div>
    <p v-if="failed" role="alert">The producers couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!producers" class="status">Loading…</p>
    <p v-else-if="!producers.length" class="status">No producers are listed yet.</p>
    <ul v-else class="producer-list">
      <li v-for="p in producers" :key="p.key">
        <ProducerCard :producer="p" :level="2" />
      </li>
    </ul>
  </article>
</template>

<style scoped>
.producer-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 22rem), 1fr));
  gap: 1rem;
  margin: 1.5rem 0 0;
  padding: 0;
  list-style: none;
}
</style>
