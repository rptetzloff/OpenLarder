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
</template>
