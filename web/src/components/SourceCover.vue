<script setup lang="ts">
import { ref, watch } from "vue";
import CoverBlank from "./CoverBlank.vue";

// A source's cover on a card. The printed face (CoverBlank) is always there,
// and the picture fades in over it once it has arrived: until then, and when
// it never arrives, the card shows the title, not an empty box or the
// browser's broken picture. Decoration only: the title is said beside it.
const props = defineProps<{
  src?: string | null;
  title: string;
  byline?: string | null;
  kind?: string;
  // In the first row of a page, where waiting to be scrolled to only delays it.
  eager?: boolean;
}>();

const arrived = ref(false);
const failed = ref(false);
// The same card can be given another source: a list re-sorted in place.
watch(
  () => props.src,
  () => {
    arrived.value = false;
    failed.value = false;
  },
);
</script>

<template>
  <span class="cover">
    <CoverBlank :title="title" :byline="byline" :kind="kind" />
    <!-- width and height give the picture's shape (2 by 3) before it loads. -->
    <img
      v-if="src && !failed"
      :src="src"
      alt=""
      width="200"
      height="300"
      :loading="eager ? 'eager' : 'lazy'"
      :class="{ arrived }"
      @load="arrived = true"
      @error="failed = true"
    />
  </span>
</template>
