<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { type IsSaved, isSaved, type OtherList, save, type State, unsave } from "../saved";

// One bar under a recipe's title (Ray's design, 2026-11-11): its rating in
// spoons with the average beside them, your own rating, and "Want to cook"
// and "Cooked"; under it, the lists shared with you that it's on, or could
// be. Signed out: the rating, and a way in.
const props = defineProps<{ recipeId: string; signedIn: boolean }>();

interface Rating {
  spoons: number | null;
  ratings: number;
  mine: number | null;
}

const rating = ref<Rating | null>(null);
const saved = ref<IsSaved | null>(null);
const busy = ref(false);
const error = ref("");
// The spoon the pointer or focus is on, to preview a rating.
const hover = ref(0);
const ratingUrl = computed(() => `/api/recipes/${props.recipeId}/rating`);
// How much of each of the five average spoons is filled: 4.3 fills four
// and three-tenths of the fifth.
const fills = computed(() =>
  [1, 2, 3, 4, 5].map((n) => Math.max(0, Math.min(1, (rating.value?.spoons ?? 0) - (n - 1)))),
);
const yours = computed(() => hover.value || rating.value?.mine || 0);
const name = (o: OtherList) => `${o.owner_name ?? "Someone"}'s list`;
const theirs = computed(() => (saved.value?.others ?? []).filter((o) => o.state));
const addable = computed(() => (saved.value?.others ?? []).filter((o) => !o.state && o.editable));

onMounted(async () => {
  try {
    const res = await fetch(ratingUrl.value);
    if (res.ok) rating.value = await res.json();
  } catch {
    // No rating shown.
  }
  if (!props.signedIn) return;
  try {
    saved.value = await isSaved(props.recipeId);
  } catch {
    // Shown as not saved; saving says what's wrong.
    saved.value = { recipe_id: props.recipeId, state: null, others: [] };
  }
});

async function act(job: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await job();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

const rate = (spoons: number | null) =>
  act(async () => {
    const res = await fetch(ratingUrl.value, {
      method: spoons ? "PUT" : "DELETE",
      headers: spoons ? { "Content-Type": "application/json" } : undefined,
      body: spoons ? JSON.stringify({ spoons }) : undefined,
    });
    if (!res.ok) throw new Error("That didn't work. Try again.");
    rating.value = spoons ? await res.json() : await (await fetch(ratingUrl.value)).json();
  });

// Each button is a toggle: pressing the one that's on takes the recipe off.
const toggle = (to: State, owner?: string, now = saved.value?.state) =>
  act(async () => {
    if (now === to) {
      await unsave(props.recipeId, owner);
      saved.value = await isSaved(props.recipeId);
    } else {
      saved.value = await save(props.recipeId, to, owner);
    }
  });
</script>

<template>
  <div v-if="rating" class="recipe-actions-bar">
    <div class="bar">
      <p class="average">
        <span class="spoons gold" aria-hidden="true">
          <span v-for="(f, i) in fills" :key="i" class="spoon">
            <svg viewBox="0 0 12 24"><use href="#spoon-shape" /></svg>
            <span class="fill" :style="{ width: `${f * 100}%` }">
              <svg viewBox="0 0 12 24"><use href="#spoon-shape" /></svg>
            </span>
          </span>
        </span>
        <template v-if="rating.ratings && rating.spoons !== null">
          <strong>{{ rating.spoons.toFixed(1) }}</strong>
          <span class="visually-hidden">of 5 spoons, from</span>
          <span class="muted"
            >{{ rating.ratings.toLocaleString() }}
            {{ rating.ratings === 1 ? "rating" : "ratings" }}</span
          >
        </template>
        <span v-else class="muted">Not rated yet</span>
      </p>
      <template v-if="signedIn">
        <div class="yours">
          <span id="rate-label" class="muted">{{ rating.mine ? "Your rating" : "Rate it" }}</span>
          <span class="spoons" role="group" aria-labelledby="rate-label">
            <button
              v-for="n in 5"
              :key="n"
              type="button"
              :class="{ on: n <= yours }"
              :aria-pressed="rating.mine === n"
              :aria-label="`${n} ${n === 1 ? 'spoon' : 'spoons'}`"
              :disabled="busy"
              @click="rate(n)"
              @mouseenter="hover = n"
              @mouseleave="hover = 0"
              @focus="hover = n"
              @blur="hover = 0"
            >
              <svg viewBox="0 0 12 24" aria-hidden="true"><use href="#spoon-shape" /></svg>
            </button>
          </span>
          <button v-if="rating.mine" type="button" class="link" :disabled="busy" @click="rate(null)">
            Clear<span class="visually-hidden"> my rating</span>
          </button>
        </div>
        <div v-if="saved" class="saves">
          <button
            type="button"
            class="secondary pill"
            :aria-pressed="saved.state === 'want'"
            :disabled="busy"
            @click="toggle('want')"
          >
            <svg viewBox="0 0 16 20" aria-hidden="true" class="icon">
              <path d="M3 2.5h10v15l-5-4-5 4z" />
            </svg>
            Want to cook
          </button>
          <button
            type="button"
            class="secondary pill"
            :aria-pressed="saved.state === 'cooked'"
            :disabled="busy"
            @click="toggle('cooked')"
          >
            <svg viewBox="0 0 20 20" aria-hidden="true" class="icon line">
              <path d="M4 10.5l4 4 8-9" />
            </svg>
            Cooked
          </button>
        </div>
      </template>
      <p v-else class="sign-in"><a href="/api/auth/login">Sign in</a> to rate or save</p>
    </div>
    <p v-if="theirs.length || addable.length" class="also muted">
      <template v-if="theirs.length"
        >Also on
        <template v-for="(o, i) in theirs" :key="o.owner_id"
          ><template v-if="i > 0">, </template><a href="/saved">{{ name(o) }}</a
          >{{ o.state === "cooked" ? " (cooked)" : ""
          }}<template v-if="o.editable">
            (<button
              type="button"
              class="link"
              :disabled="busy"
              :aria-label="`Take it off ${name(o)}`"
              @click="toggle(o.state!, o.owner_id, o.state)"
            >
              take off</button
            >)</template
          ></template
        ></template
      ><template v-for="(o, i) in addable" :key="o.owner_id"
        ><template v-if="theirs.length || i > 0"> · </template
        ><button type="button" class="link" :disabled="busy" @click="toggle('want', o.owner_id, null)">
          Add to {{ name(o) }}
        </button></template
      >
    </p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <!-- The spoon, drawn once: a bowl and a handle. -->
    <svg width="0" height="0" class="defs" aria-hidden="true">
      <defs>
        <g id="spoon-shape">
          <ellipse cx="6" cy="6.5" rx="4" ry="5.25" />
          <rect x="4.75" y="11" width="2.5" height="12" rx="1.25" />
        </g>
      </defs>
    </svg>
  </div>
</template>

<style scoped>
.recipe-actions-bar {
  margin: 0.75rem 0 1.25rem;
}
.bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1.25rem;
  padding: 0.625rem 1rem;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
}
.bar p {
  margin: 0;
}
.average,
.yours {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.average strong {
  font-size: 1.125rem;
}
.yours {
  padding-left: 1.25rem;
  border-left: 1px solid var(--line);
}
.saves,
.sign-in {
  margin-left: auto;
}
.saves {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.spoons {
  display: inline-flex;
  align-items: center;
}
.spoons svg {
  display: block;
  width: 0.875rem;
  height: 1.75rem;
  fill: none;
  stroke: var(--border);
  stroke-width: 1;
}
/* The average: each spoon an outline, with as much of a gold one over it
   as the average fills. Decorative; the number beside it says it. */
.spoon {
  position: relative;
  margin-right: 0.3rem;
}
.spoon .fill {
  position: absolute;
  inset: 0 auto 0 0;
  overflow: hidden;
}
.spoon .fill svg {
  fill: var(--spoon);
  stroke: var(--spoon);
}
/* Yours: buttons, with room for a thumb. */
.spoons button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 2.25rem;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: none;
  cursor: pointer;
}
.spoons button.on svg {
  fill: var(--fg);
  stroke: var(--fg);
}
.pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border-radius: 999px;
  font-weight: 600;
  background: var(--surface);
}
.icon {
  width: 0.9rem;
  height: 1.1rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.75;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.pill[aria-pressed="true"] .icon:not(.line) {
  fill: currentColor;
}
.also {
  margin: 0.4rem 0 0;
  font-size: 0.9375rem;
}
.defs {
  position: absolute;
}
@media (max-width: 40rem) {
  .yours {
    padding-left: 0;
    border-left: 0;
  }
  .saves,
  .sign-in {
    margin-left: 0;
  }
}
</style>
