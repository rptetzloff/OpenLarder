<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

// A recipe's rating (routers/ratings.py): one to five spoons. Everyone
// sees the average and how many gave it; signed in, the spoons are buttons
// that give yours. Ray, 2026-11-11: "spoons or forks or salamanders".
const props = defineProps<{ recipeId: string; signedIn: boolean }>();

interface Rating {
  spoons: number | null;
  ratings: number;
  mine: number | null;
}

const rating = ref<Rating | null>(null);
const busy = ref(false);
const error = ref("");
// The spoon the pointer or focus is on, to preview a rating.
const hover = ref(0);
const url = computed(() => `/api/recipes/${props.recipeId}/rating`);
// Yours when you've given one, else the average, to the nearest spoon.
const filled = computed(
  () => hover.value || rating.value?.mine || Math.round(rating.value?.spoons ?? 0),
);
const summary = computed(() => {
  const r = rating.value;
  if (!r || !r.ratings || r.spoons === null) return "Not rated yet";
  return `${r.spoons} of 5 spoons, from ${r.ratings.toLocaleString()} ${
    r.ratings === 1 ? "rating" : "ratings"
  }`;
});

onMounted(async () => {
  try {
    const res = await fetch(url.value);
    if (res.ok) rating.value = await res.json();
  } catch {
    // No rating shown.
  }
});

async function act(method: "PUT" | "DELETE", spoons?: number) {
  busy.value = true;
  error.value = "";
  try {
    const res = await fetch(url.value, {
      method,
      headers: spoons ? { "Content-Type": "application/json" } : undefined,
      body: spoons ? JSON.stringify({ spoons }) : undefined,
    });
    if (!res.ok) throw new Error("That didn't work. Try again.");
    rating.value = method === "PUT" ? await res.json() : await (await fetch(url.value)).json();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div v-if="rating" class="spoon-rating">
    <div v-if="signedIn" class="spoons" role="group" aria-label="Your rating">
      <button
        v-for="n in 5"
        :key="n"
        type="button"
        :class="{ on: n <= filled }"
        :aria-pressed="rating.mine === n"
        :aria-label="`${n} ${n === 1 ? 'spoon' : 'spoons'}`"
        :disabled="busy"
        @click="act('PUT', n)"
        @mouseenter="hover = n"
        @mouseleave="hover = 0"
        @focus="hover = n"
        @blur="hover = 0"
      >
        <svg viewBox="0 0 12 24" aria-hidden="true">
          <ellipse cx="6" cy="6.5" rx="4.25" ry="5.5" />
          <rect x="5" y="11" width="2" height="12" rx="1" />
        </svg>
      </button>
    </div>
    <span v-else class="spoons" aria-hidden="true">
      <span v-for="n in 5" :key="n" :class="{ on: n <= filled }">
        <svg viewBox="0 0 12 24">
          <ellipse cx="6" cy="6.5" rx="4.25" ry="5.5" />
          <rect x="5" y="11" width="2" height="12" rx="1" />
        </svg>
      </span>
    </span>
    <span class="spoon-summary">
      {{ summary }}<template v-if="rating.mine">
        · yours: {{ rating.mine }}
        <button type="button" class="link" :disabled="busy" @click="act('DELETE')">
          Clear my rating
        </button></template
      ><template v-else-if="signedIn"> · choose a spoon to rate it</template
      ><template v-else> · <a href="/api/auth/login">sign in</a> to rate it</template>
    </span>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.spoon-rating {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 0.75rem;
  margin: 0.5rem 0;
}
.spoons {
  display: inline-flex;
  gap: 0.125rem;
}
.spoons button,
.spoons > span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  /* A target big enough for a thumb. */
  width: 1.75rem;
  height: 2.25rem;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: none;
  color: var(--fg);
}
.spoons button {
  cursor: pointer;
}
.spoons svg {
  width: 0.875rem;
  height: 1.75rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.25;
}
.spoons .on svg {
  fill: currentColor;
}
.spoon-summary {
  color: var(--muted);
  font-size: 0.9375rem;
}
.spoon-rating .error {
  flex-basis: 100%;
  margin: 0;
}
</style>
