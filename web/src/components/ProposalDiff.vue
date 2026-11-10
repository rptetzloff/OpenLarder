<script setup lang="ts">
import { computed } from "vue";
import type { Proposal } from "../review";

// A proposed change beside the recipe as it is: only what differs.
const props = defineProps<{ proposal: Proposal }>();
const rows = computed(() => {
  const { current: a, proposed: b } = props.proposal;
  const out: { label: string; now: string; then: string }[] = [];
  if (a.title !== b.title) out.push({ label: "Title", now: a.title, then: b.title });
  if ((a.chapter ?? "") !== (b.chapter ?? ""))
    out.push({ label: "Chapter", now: a.chapter ?? "none", then: b.chapter ?? "none" });
  if (a.places.join("\n") !== b.places.join("\n"))
    out.push({ label: "Where", now: a.places.join("; ") || "none", then: b.places.join("; ") || "none" });
  if (a.ingredients.join("\n") !== b.ingredients.join("\n"))
    out.push({
      label: "Ingredients",
      now: a.ingredients.join("; ") || "none",
      then: b.ingredients.join("; ") || "none",
    });
  return out;
});
</script>

<template>
  <table v-if="rows.length" class="recipe-table proposal-diff">
    <thead>
      <tr>
        <th scope="col"><span class="visually-hidden">What</span></th>
        <th scope="col">Now</th>
        <th scope="col">Proposed</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="r in rows" :key="r.label">
        <th scope="row">{{ r.label }}</th>
        <td><span class="cell-label">Now </span>{{ r.now }}</td>
        <td><span class="cell-label">Proposed </span>{{ r.then }}</td>
      </tr>
    </tbody>
  </table>
  <p v-else class="muted">It's the same as the recipe is now.</p>
</template>
