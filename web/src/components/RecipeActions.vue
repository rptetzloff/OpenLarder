<script setup lang="ts">
import SignInLink from "./SignInLink.vue";
import { computed, nextTick, onMounted, ref } from "vue";
import { type IsSaved, isSaved, type OtherList, save, type State, unsave } from "../saved";
import PillToggle from "./PillToggle.vue";

// One bar under a recipe's title (Ray's cleanup pass, section 1,
// 2026-11-11): its rating in spoons with the average beside them, your own
// rating, and "Want to cook" and "Cooked". Under it, the lists shared with
// you that it's on, or could be. Signed out: the rating, and a way in.
// The bar never changes shape: saving, rating and clearing change fills and
// labels only, and each is said in the live region.
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
// Said to a screen reader after each change.
const said = ref("");
// The spoon the pointer is on, to preview a rating.
const hover = ref(0);
const adding = ref(false);
const radios = ref<HTMLButtonElement[]>([]);
const ratingUrl = computed(() => `/api/recipes/${props.recipeId}/rating`);
// How much of each of the five average spoons is filled: 4.3 fills four
// and three-tenths of the fifth.
const fills = computed(() =>
  [1, 2, 3, 4, 5].map((n) => Math.max(0, Math.min(1, (rating.value?.spoons ?? 0) - (n - 1)))),
);
const yours = computed(() => hover.value || rating.value?.mine || 0);
// The one radio in the Tab order: the one chosen, or the first.
const tabStop = computed(() => rating.value?.mine || 1);
const average = computed(() => {
  const r = rating.value;
  if (!r || !r.ratings || r.spoons === null) return "Not rated yet";
  return `Rated ${r.spoons.toFixed(1)} of 5 spoons from ${r.ratings.toLocaleString()} ${
    r.ratings === 1 ? "rating" : "ratings"
  }`;
});
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

async function act(job: () => Promise<string>) {
  busy.value = true;
  error.value = "";
  said.value = "";
  try {
    said.value = await job();
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
    return spoons ? `Rated ${spoons} ${spoons === 1 ? "spoon" : "spoons"}` : "Rating cleared";
  });

// The radio group's keys: arrows move and choose, wrapping at the ends.
async function onKey(event: KeyboardEvent, n: number) {
  const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
  if (!step) return;
  event.preventDefault();
  const to = ((n - 1 + step + 5) % 5) + 1;
  await rate(to);
  await nextTick();
  radios.value[to - 1]?.focus();
}

// Each button is a toggle: pressing the one that's on takes the recipe off.
const toggle = (to: State) =>
  act(async () => {
    if (saved.value?.state === to) {
      await unsave(props.recipeId);
      saved.value = await isSaved(props.recipeId);
      return "Removed from your list";
    }
    saved.value = await save(props.recipeId, to);
    return to === "want" ? "Saved to want to cook" : "Marked as cooked";
  });

const addTo = (o: OtherList) =>
  act(async () => {
    saved.value = await save(props.recipeId, "want", o.owner_id);
    adding.value = false;
    return `Saved to ${name(o)}`;
  });
const takeOff = (o: OtherList) =>
  act(async () => {
    await unsave(props.recipeId, o.owner_id);
    saved.value = await isSaved(props.recipeId);
    return `Removed from ${name(o)}`;
  });
</script>

<template>
  <div v-if="rating" class="recipe-actions-bar">
    <div class="bar">
      <div class="rating">
        <p class="average">
          <span class="spoons" aria-hidden="true">
            <span v-for="(f, i) in fills" :key="i" class="spoon">
              <svg viewBox="0 0 16 28"><use href="#spoon-shape" /></svg>
              <span class="fill" :style="{ width: `${f * 100}%` }">
                <svg viewBox="0 0 16 28"><use href="#spoon-shape" /></svg>
              </span>
            </span>
          </span>
          <span class="visually-hidden">{{ average }}</span>
          <template v-if="rating.ratings && rating.spoons !== null">
            <strong aria-hidden="true">{{ rating.spoons.toFixed(1) }}</strong>
            <span class="muted" aria-hidden="true"
              >{{ rating.ratings.toLocaleString() }}
              {{ rating.ratings === 1 ? "rating" : "ratings" }}</span
            >
          </template>
          <span v-else class="muted" aria-hidden="true">Not rated yet</span>
        </p>
        <div v-if="signedIn" class="yours">
          <span class="muted yours-label" aria-hidden="true">{{
            rating.mine ? "Your rating" : "Rate it"
          }}</span>
          <span class="spoons radios" role="radiogroup" aria-label="Your rating">
            <button
              v-for="n in 5"
              :key="n"
              ref="radios"
              type="button"
              role="radio"
              :class="{ on: n <= yours }"
              :aria-checked="rating.mine === n"
              :aria-label="`${n} ${n === 1 ? 'spoon' : 'spoons'}`"
              :tabindex="n === tabStop ? 0 : -1"
              :disabled="busy"
              @click="rate(n)"
              @keydown="onKey($event, n)"
              @mouseenter="hover = n"
              @mouseleave="hover = 0"
            >
              <svg viewBox="0 0 16 28" aria-hidden="true"><use href="#spoon-shape" /></svg>
            </button>
          </span>
          <!-- Kept in place when there's nothing to clear, so nothing moves. -->
          <button
            type="button"
            class="link clear"
            :class="{ unseen: !rating.mine }"
            :disabled="busy || !rating.mine"
            :aria-hidden="!rating.mine"
            :tabindex="rating.mine ? 0 : -1"
            @click="rate(null)"
          >
            Clear<span class="visually-hidden"> my rating</span>
          </button>
        </div>
      </div>
      <div v-if="signedIn && saved" class="saves">
        <PillToggle
          :pressed="saved.state === 'want'"
          icon="bookmark"
          :disabled="busy"
          @toggle="toggle('want')"
          >Want to cook</PillToggle
        >
        <PillToggle
          :pressed="saved.state === 'cooked'"
          icon="check"
          :disabled="busy"
          @toggle="toggle('cooked')"
          >Cooked</PillToggle
        >
      </div>
      <p v-else-if="!signedIn" class="sign-in">
        <SignInLink /> to rate or save
      </p>
    </div>
    <div v-if="theirs.length || addable.length" class="also muted">
      <span v-if="theirs.length"
        >Also on
        <template v-for="(o, i) in theirs" :key="o.owner_id"
          ><template v-if="i > 0">, </template><a href="/saved">{{ name(o) }}</a
          >{{ o.state === "cooked" ? " (cooked)" : ""
          }}<template v-if="o.editable">
            <button
              type="button"
              class="link"
              :disabled="busy"
              :aria-label="`Take it off ${name(o)}`"
              @click="takeOff(o)"
            >
              take off
            </button></template
          ></template
        ></span
      >
      <template v-if="addable.length">
        <span v-if="theirs.length" aria-hidden="true"> · </span>
        <button
          type="button"
          class="link"
          :aria-expanded="adding"
          aria-controls="add-to-lists"
          @click="adding = !adding"
        >
          Add to another list
        </button>
        <ul v-show="adding" id="add-to-lists" class="lists">
          <li v-for="o in addable" :key="o.owner_id">
            <button type="button" class="secondary small" :disabled="busy" @click="addTo(o)">
              {{ name(o) }}
            </button>
          </li>
        </ul>
      </template>
    </div>
    <p class="visually-hidden" aria-live="polite">{{ said }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <!-- The spoon, drawn once: a bowl and a handle (the spec's shape). -->
    <svg width="0" height="0" class="defs" aria-hidden="true">
      <defs>
        <g id="spoon-shape">
          <ellipse cx="8" cy="8" rx="5.6" ry="7.2" />
          <rect x="6.5" y="13.5" width="3" height="13.5" rx="1.5" />
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
  justify-content: space-between;
  gap: 0.5rem 1.25rem;
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.bar p {
  margin: 0;
}
.rating {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem 1.25rem;
}
.average,
.yours {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 2.75rem;
}
.average strong {
  font-size: var(--text-lg);
}
.yours {
  padding-left: 1.25rem;
  border-left: 1px solid var(--line);
}
/* Wide enough for either label, so the spoons don't move when it changes. */
.yours-label {
  min-width: 5.25rem;
}
.saves {
  display: flex;
  gap: 0.5rem;
}
.spoons {
  display: inline-flex;
  align-items: center;
}
/* 24px tall. Empty: a 1.3px outline. */
.spoons svg {
  display: block;
  width: 0.857rem;
  height: 1.5rem;
  fill: none;
  stroke: var(--border);
  stroke-width: 1.3;
}
/* The average: each spoon an outline, with as much of a mustard one over
   it as the average fills. Decorative; the number beside it says it. */
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
  fill: var(--rating);
  stroke: var(--rating);
}
/* Yours: radio buttons, 44px tall, and 44px wide where a finger taps. */
.radios button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 2.75rem;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: none;
  cursor: pointer;
}
@media (pointer: coarse) {
  .radios button {
    width: 2.75rem;
  }
}
.radios button.on svg {
  fill: var(--fg);
  stroke: var(--fg);
}
.clear {
  min-height: 2.75rem;
  padding: 0 0.25rem;
}
.unseen {
  visibility: hidden;
}
.also {
  margin: 0.4rem 0 0;
  font-size: var(--text-sm);
}
.also .link {
  min-height: 2.75rem;
}
.lists {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  list-style: none;
  padding: 0;
  margin: 0.25rem 0 0;
}
.defs {
  position: absolute;
}
/* Phone: the average, then yours, then the two buttons side by side. */
@media (max-width: 40rem) {
  .bar,
  .rating {
    flex-direction: column;
    align-items: stretch;
  }
  .yours {
    padding-left: 0;
    border-left: 0;
  }
  .saves > * {
    flex: 1 1 0;
  }
}
</style>
