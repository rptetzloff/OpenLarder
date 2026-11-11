<script setup lang="ts">
import type { Proposal } from "../review";

// A proposed change beside the record as it is: only what differs.
defineProps<{ proposal: Proposal }>();
</script>

<template>
  <table v-if="proposal.differences.length" class="recipe-table proposal-diff">
    <thead>
      <tr>
        <th scope="col"><span class="visually-hidden">What</span></th>
        <th scope="col">Now</th>
        <th scope="col">Proposed</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="d in proposal.differences" :key="d.label">
        <th scope="row">{{ d.label }}</th>
        <td><span class="cell-label">Now </span>{{ d.now }}</td>
        <td><span class="cell-label">Proposed </span>{{ d.proposed }}</td>
      </tr>
    </tbody>
  </table>
  <p v-else class="muted">It's the same as it is now.</p>
  <div v-if="proposal.new_ingredients?.length" class="review-new">
    <p>
      Applying it adds {{ proposal.new_ingredients.length === 1 ? "a new ingredient" : "new ingredients" }}.
      If {{ proposal.new_ingredients.length === 1 ? "it's" : "one is" }} an ingredient already
      here written differently, decline and say which.
    </p>
    <ul>
      <li v-for="n in proposal.new_ingredients" :key="n.name">
        {{ n.name }}
        <template v-if="n.similar.length">
          <span class="muted"> · like </span>
          <template v-for="(s, i) in n.similar" :key="s.id"
            ><template v-if="i">, </template><a :href="`/ingredients/${s.id}`">{{ s.name }}</a></template
          >
        </template>
      </li>
    </ul>
  </div>
</template>
