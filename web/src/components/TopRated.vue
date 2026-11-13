<script setup lang="ts">
// A source's or an author's top rated recipes, best first (Ray, 2026-11-12;
// routers/ratings.py): those averaging four spoons or more, at most five,
// once three of its recipes are rated. The order weighs how many rated each,
// so one person's five can come after two people's four and five.
// Left off when there are none, not filled with some other ranking.
import { issueName } from "../books";
import type { Listed } from "../ingredients";

defineProps<{
  recipes: Listed[];
  // On an author's page: each recipe's source, which there isn't one of.
  withSource?: boolean;
}>();

// Where it is in its source: the issue or the episode, and the page.
function place(r: Listed): string {
  const parts: string[] = [];
  if (r.issue) parts.push(issueName(r.issue));
  if (r.episode) parts.push(r.at ? `${r.episode}, at ${r.at}` : r.episode);
  const pages = [...new Set(r.pages)];
  if (pages.length) parts.push(`p. ${pages.join(" / ")}`);
  return parts.join(" · ");
}

function rating(r: Listed): string {
  const from = r.ratings === 1 ? "1 rating" : `${(r.ratings ?? 0).toLocaleString()} ratings`;
  return `${r.spoons} of 5 spoons, from ${from}`;
}
</script>

<template>
  <section v-if="recipes.length" class="source-section" aria-labelledby="top-rated-title">
    <h2 id="top-rated-title">Top rated</h2>
    <ol class="top-rated">
      <li v-for="r in recipes" :key="r.id">
        <a :href="`/recipes/${r.id}`" class="strong">{{ r.title }}</a>
        <span class="about muted">
          <template v-if="withSource"
            ><a :href="`/sources/${r.source_id}`">{{ r.source_title }}</a> ·
          </template>
          <template v-if="place(r)">{{ place(r) }} · </template>{{ rating(r) }}
        </span>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.top-rated {
  margin: 0;
  padding-left: 1.5rem;
}
.top-rated li {
  margin-bottom: 0.5rem;
}
.strong {
  font-weight: 600;
}
.about {
  display: block;
  font-size: var(--text-sm);
}
</style>
