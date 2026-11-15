<script setup lang="ts">
// A producer, on its own page and on the ingredients it supplies (Ray's
// round 4 list, part D4, 2026-11-13). What its link earns, and for whom,
// is said directly beside the link, wherever the card is.
import { computed } from "vue";
import { type Producer, type ProducerCard, visitHref } from "../producers";

const props = defineProps<{
  producer: ProducerCard | Producer;
  // On an ingredient's page: the description cut short, and not what else
  // it supplies or each state by name.
  brief?: boolean;
  // The heading its name is, under whatever the page has above it.
  level: 2 | 3 | 4;
}>();
const whole = computed(() =>
  !props.brief && "supplies" in props.producer ? props.producer : null,
);
</script>

<template>
  <div class="producer-card" :class="{ brief }">
    <component :is="`h${level}`" class="producer-name">{{ producer.label }}</component>
    <p v-if="producer.description" class="producer-about">{{ producer.description }}</p>
    <p v-if="whole?.supplies.length" class="producer-supplies">
      Supplies
      <template v-for="(i, n) in whole.supplies" :key="i.id"
        ><template v-if="n > 0">, </template
        ><a :href="`/ingredients/${i.id}`">{{ i.name.toLowerCase() }}</a></template
      >
    </p>
    <!-- On an ingredient's page the offer and where it ships share a line:
         two cards stand above the recipes there, and each line they take
         is one the list is pushed down by. -->
    <p v-if="brief" class="producer-facts">
      <strong v-if="producer.offer">{{ producer.offer }}</strong
      ><template v-if="producer.offer"> · </template>{{ producer.ships }}
    </p>
    <template v-else>
      <p v-if="producer.offer" class="producer-offer">{{ producer.offer }}</p>
      <details v-if="whole?.states.length && whole.states.length > 1" class="producer-ships">
        <summary>{{ producer.ships }}</summary>
        <p>{{ whole.states.join(", ") }}</p>
      </details>
      <p v-else class="producer-ships">{{ producer.ships }}</p>
    </template>
    <!-- "Visit" alone, twice on a page, says nothing in a list of links. -->
    <a
      :href="visitHref(producer)"
      class="primary small"
      :rel="producer.earns === 'none' ? 'noopener' : 'sponsored noopener'"
      >Visit {{ producer.label }}</a
    >
    <p class="buy-note">{{ producer.disclosure }}</p>
  </div>
</template>

<style scoped>
.producer-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
}
.producer-card p,
.producer-name {
  margin: 0;
}
.producer-name {
  font-size: 1.125rem;
}
.producer-offer {
  font-weight: 600;
}
.producer-ships {
  color: var(--muted);
  font-size: 0.875rem;
}
.producer-ships summary {
  /* A finger's height: it opens the list of states. */
  min-height: 2.75rem;
  display: flex;
  align-items: center;
  cursor: pointer;
}
.producer-ships summary::before {
  content: "▸";
  margin-right: 0.375rem;
}
.producer-ships[open] summary::before {
  content: "▾";
}
.producer-card .primary {
  margin-top: 0.375rem;
}
/* On an ingredient's page it's beside the point of the page: one line of
   what the producer is (Ray's spec), the whole of it on its own page. */
.brief {
  gap: 0.25rem;
  padding: 0.75rem;
}
.brief .producer-name {
  font-size: 1rem;
}
.brief .producer-about {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
  line-clamp: 1;
}
.producer-facts {
  font-size: 0.875rem;
}
</style>
