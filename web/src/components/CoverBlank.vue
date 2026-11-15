<script setup lang="ts">
import { computed } from "vue";
import { KIND_NAMES } from "../books";
import { coverColor } from "../coverColor";

// A cover drawn for a source: its title and byline, set like a printed
// cover on a colour picked from the title, so a shelf of them isn't one
// colour. A source with no picture keeps it; one with a picture shows it
// until the picture arrives (SourceCover.vue). Decoration only: the title is
// said beside it. *Ray, 2026-11-10.*
const props = defineProps<{ title: string; byline?: string | null; kind?: string }>();

const colour = computed(() => coverColor(props.title));
</script>

<template>
  <span class="cover-blank" :style="{ '--cover': colour }" aria-hidden="true"
    ><span class="cover-face">
    <span v-if="kind && kind !== 'book'" class="cover-kind">{{ KIND_NAMES[kind] ?? kind }}</span>
    <span class="cover-title">{{ title }}</span>
    <span v-if="byline" class="cover-byline">{{ byline }}</span>
  </span></span>
</template>
