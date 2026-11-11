<script setup lang="ts">
import { computed } from "vue";
import { KIND_NAMES } from "../books";

// A cover for a source with none: its title and byline, set like a printed
// cover on a colour picked from the title, so a shelf of them isn't one
// colour. Decoration only: the title is said beside it. *Ray, 2026-11-10.*
const props = defineProps<{ title: string; byline?: string | null; kind?: string }>();

// Each dark enough for the cream and gold text (4.5:1 or better).
const COLOURS = ["#2e4a3b", "#7a3418", "#2b3f57", "#5a3350", "#3d4a1e"];
const colour = computed(() => {
  let h = 0;
  for (const c of props.title) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return COLOURS[h % COLOURS.length];
});
</script>

<template>
  <span class="cover-blank" :style="{ '--cover': colour }" aria-hidden="true"
    ><span class="cover-face">
    <span v-if="kind && kind !== 'book'" class="cover-kind">{{ KIND_NAMES[kind] ?? kind }}</span>
    <span class="cover-title">{{ title }}</span>
    <span v-if="byline" class="cover-byline">{{ byline }}</span>
  </span></span>
</template>
