<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { coverColor } from "../coverColor";

// A source's cover beside a recipe in a list (search results, saved
// recipes, notes): the picture, on a block of the colour its drawn cover
// has (Ray's round 5 list, item 3, 2026-11-15). A source with no picture
// was an empty white box here, where everywhere else it's the drawn cover.
// No words on it: at this size they couldn't be read, and the title is
// beside it. The block is there until the picture arrives, and stays if
// it never does. Decoration only.
const props = defineProps<{ src?: string | null; title: string }>();

const colour = computed(() => coverColor(props.title));
const arrived = ref(false);
const failed = ref(false);
// The same row can be given another recipe: a list re-sorted in place.
watch(
  () => props.src,
  () => {
    arrived.value = false;
    failed.value = false;
  },
);
</script>

<template>
  <span class="hit-cover" :style="{ '--cover': colour }" aria-hidden="true">
    <img
      v-if="src && !failed"
      :src="src"
      alt=""
      loading="lazy"
      :class="{ arrived }"
      @load="arrived = true"
      @error="failed = true"
    />
  </span>
</template>
