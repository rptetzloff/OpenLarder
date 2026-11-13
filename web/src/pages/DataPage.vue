<script setup lang="ts">
import { onMounted, ref } from "vue";
import { type Dumps, listDumps, size } from "../dumps";

// The whole public catalog to download, weekly, under the ODbL (dumps.py).
document.title = "Open data · OpenLarder";

const dumps = ref<Dumps | null>(null);
const error = ref("");
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "long" });

onMounted(async () => {
  try {
    dumps.value = await listDumps();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
});
</script>

<template>
  <article>
    <h1>Open data</h1>
    <p>
      OpenLarder's catalog is open data: every source, recipe, page and ingredient name anyone can
      see here, and each recipe's average rating, free to download and reuse. It's built fresh
      each week, in two forms with the same contents.
    </p>
    <ul>
      <li><strong>CSV</strong>: one file per table, for spreadsheets and databases.</li>
      <li>
        <strong>JSON Lines</strong>: one record a line, each recipe with its pages and ingredients
        inside it, for programs.
      </li>
    </ul>
    <p>
      Private family collections and anything waiting for review are left out, and nothing about
      accounts is included: a rating is the average and how many gave one, never who. To read a
      little at a time, there's the
      <a href="/api/docs">API</a> instead.
    </p>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-else-if="!dumps" class="status">Loading…</p>
    <template v-else>
      <section v-if="dumps.latest" class="tool-panel" aria-labelledby="latest-title">
        <h2 id="latest-title">The latest, from {{ day(dumps.latest.built_at) }}</h2>
        <p class="muted">
          {{ (dumps.latest.counts.recipes ?? 0).toLocaleString() }} recipes in
          {{ (dumps.latest.counts.sources ?? 0).toLocaleString() }} sources, with
          {{ (dumps.latest.counts.ingredients ?? 0).toLocaleString() }} ingredients.
        </p>
        <p class="row-actions">
          <a :href="dumps.latest.csv_url" class="secondary">CSV ({{ size(dumps.latest.csv_bytes) }})</a>
          <a :href="dumps.latest.json_url" class="secondary"
            >JSON Lines ({{ size(dumps.latest.json_bytes) }})</a
          >
        </p>
      </section>
      <p v-else class="status">
        {{ dumps.available ? "The first one is on its way." : "Downloads aren't available yet." }}
      </p>

      <h2>Using it</h2>
      <p>
        It's under the
        <a :href="dumps.licence_url">Open Database License (ODbL)</a>: you may copy, share and build
        on it, if you credit OpenLarder and keep any database you make from it open under the same
        licence. Credit it like this:
      </p>
      <blockquote class="attribution">{{ dumps.attribution }}</blockquote>
      <p>
        Each download has a README listing its tables and what's in them. Book details come from
        Open Library and author facts from Wikidata, both public domain.
      </p>

      <template v-if="dumps.older.length">
        <h2>Earlier weeks</h2>
        <p class="muted">
          Each week's is kept for
          {{ dumps.keep_days === 365 ? "a year" : `${dumps.keep_days} days` }}.
        </p>
        <ul class="dump-list">
          <li v-for="d in dumps.older" :key="d.built_at">
            {{ day(d.built_at) }}:
            <a :href="d.csv_url">CSV</a> ({{ size(d.csv_bytes) }}),
            <a :href="d.json_url">JSON Lines</a> ({{ size(d.json_bytes) }})
          </li>
        </ul>
      </template>
    </template>
  </article>
</template>
