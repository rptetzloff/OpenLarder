<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { type BookSummary, KIND_NAMES } from "../books";
import SourceCover from "./SourceCover.vue";

// The home page's sources, as one row that scrolls sideways (Ray's cleanup
// pass, section 4): cards that snap into place, an arrow at each end while
// there's further to go, a fade on the right while more remains, and a last
// card to browse them all. Arrow keys scroll it once it has focus.
const props = defineProps<{
  sources: BookSummary[];
  // The heading's id, to name the row.
  labelledby: string;
}>();

const scroller = ref<HTMLElement | null>(null);
const canLeft = ref(false);
const canRight = ref(false);

function measure() {
  const el = scroller.value;
  if (!el) return;
  canLeft.value = el.scrollLeft > 1;
  canRight.value = el.scrollLeft + el.clientWidth < el.scrollWidth - 1;
}
// One visible page, less a sliver so the card at the edge stays in view;
// at once when the device asks for no motion.
function page(direction: 1 | -1) {
  const el = scroller.value;
  if (!el) return;
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  el.scrollBy({ left: direction * el.clientWidth * 0.9, behavior: still ? "auto" : "smooth" });
}

let watcher: ResizeObserver | undefined;
onMounted(() => {
  measure();
  watcher = new ResizeObserver(measure);
  if (scroller.value) watcher.observe(scroller.value);
});
onBeforeUnmount(() => watcher?.disconnect());
watch(
  () => props.sources.length,
  () => nextTick(measure),
);

// Under a card's title: who made it, or the site, then how many recipes.
function byline(s: BookSummary) {
  const who = s.authors.join(", ") || s.host;
  const count = `${s.recipes} ${s.recipes === 1 ? "recipe" : "recipes"}`;
  return who ? `${who} · ${count}` : count;
}
</script>

<template>
  <div class="source-row" :class="{ more: canRight }">
    <button
      v-show="canLeft"
      type="button"
      class="arrow left"
      aria-label="Scroll sources left"
      @click="page(-1)"
    >
      <svg viewBox="0 0 10 16" aria-hidden="true"><path d="M8 1L2 8l6 7" /></svg>
    </button>
    <div
      ref="scroller"
      class="scroller"
      tabindex="0"
      role="group"
      :aria-labelledby="labelledby"
      @scroll.passive="measure"
    >
      <ul>
        <li v-for="s in sources" :key="s.id">
          <a :href="`/sources/${s.id}`" class="cover-card">
            <SourceCover
              :src="s.cover_url"
              :title="s.title"
              :byline="s.authors.join(', ') || s.host"
              :kind="s.kind"
            />
            <span class="kind">{{ KIND_NAMES[s.kind] }}</span>
            <strong>{{ s.title }}</strong>
            <span class="byline">{{ byline(s) }}</span>
          </a>
        </li>
        <li>
          <a href="/sources" class="cover-card browse-all">
            <span class="browse-tile">
              Browse all sources
              <svg viewBox="0 0 16 10" aria-hidden="true"><path d="M1 5h13M10 1l4 4-4 4" /></svg>
            </span>
          </a>
        </li>
      </ul>
    </div>
    <button
      v-show="canRight"
      type="button"
      class="arrow right"
      aria-label="Scroll sources right"
      @click="page(1)"
    >
      <svg viewBox="0 0 10 16" aria-hidden="true"><path d="M2 1l6 7-6 7" /></svg>
    </button>
  </div>
</template>

<style scoped>
.source-row {
  position: relative;
  /* A card's width; its cover is half as tall again. */
  --card: 9.5rem;
}
.scroller {
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  /* Room for the focus ring, which the scroller would otherwise clip. */
  padding: 0.25rem;
  margin: -0.25rem;
  scroll-padding-left: 0.25rem;
  /* No scrollbar under the covers: the arrows, a finger or the arrow keys
     move it, and the fade says there's more. */
  scrollbar-width: none;
}
.scroller::-webkit-scrollbar {
  display: none;
}
ul {
  display: flex;
  gap: 1.25rem;
  list-style: none;
  margin: 0;
  padding: 0;
}
li {
  flex: 0 0 auto;
  width: var(--card);
  margin: 0;
  scroll-snap-align: start;
}
/* While more remains to the right, it fades out there. */
.source-row.more::after {
  content: "";
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 3.5rem;
  background: linear-gradient(to right, transparent, var(--bg));
  pointer-events: none;
}
.arrow {
  position: absolute;
  /* Centred on the covers. */
  top: calc(var(--card) * 0.75 - 1.375rem);
  z-index: 2;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.75rem;
  height: 2.75rem;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--surface);
  color: var(--fg);
  cursor: pointer;
}
.arrow:hover {
  border-color: var(--fg);
}
.arrow.left {
  left: -1rem;
}
.arrow.right {
  right: -1rem;
}
.arrow svg {
  width: 0.625rem;
  height: 1rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.75;
  stroke-linecap: round;
  stroke-linejoin: round;
}
/* A finger scrolls it; the arrows are for a mouse. */
@media (hover: none), (pointer: coarse) {
  .arrow {
    display: none;
  }
}
.browse-tile {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 0.5rem;
  box-sizing: border-box;
  width: 100%;
  aspect-ratio: 2 / 3;
  padding: 1rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--link);
  font-weight: 600;
  text-decoration: underline;
}
.browse-tile svg {
  width: 1rem;
  height: 0.625rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
@media (max-width: 40rem) {
  .source-row {
    --card: 8rem;
  }
}
</style>
