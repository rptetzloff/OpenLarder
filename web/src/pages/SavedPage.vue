<script setup lang="ts">
import CoverThumb from "../components/CoverThumb.vue";
import SignInLink from "../components/SignInLink.vue";
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { whereItIs } from "../ingredients";
import type { Me } from "../me";
import { allNotes, type NotedRecipe } from "../notes";
import { mySaved, save, type Saved, type SavedRecipe, shareSaved, type State, unsave } from "../saved";

// Saved recipes (routers/saved.py): what you want to cook and what you
// have, then the lists shared with you. SCOPING.md: "Saves, likes, 'want to
// cook' lists"; shared with household groups as the shelf is.
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Saved recipes · OpenLarder";

const saved = ref<Saved | null>(null);
const error = ref("");
const busy = ref(false);
const sharing = ref(false);
// Want to cook, cooked, or the recipes with notes you can see
// (routers/notes.py), which needn't be saved.
const tab = ref<State | "notes">(location.hash === "#notes" ? "notes" : "want");
const notes = ref<NotedRecipe[]>([]);
const when = (at: string) =>
  new Date(at).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });

// Yours, then each shared with you: one layout for both.
const lists = computed(() =>
  saved.value
    ? [
        { key: "mine", owner: undefined, title: "", note: "", editable: true, recipes: saved.value.recipes },
        ...saved.value.shared.map((s) => ({
          key: s.owner_id,
          owner: s.owner_id as string | undefined,
          title: `${s.owner_name ?? "Someone"}'s list`,
          note: `Shared with you through ${s.through.map((g) => g.name).join(", ")}${
            s.editable ? "" : ": you can see it, not change it"
          }.`,
          editable: s.editable,
          recipes: s.recipes,
        })),
      ]
    : [],
);
const every = computed(() => lists.value.flatMap((l) => l.recipes));
const count = (state: State) => new Set(every.value.filter((r) => r.state === state).map((r) => r.id)).size;
const of = (recipes: SavedRecipe[]) => recipes.filter((r) => r.state === tab.value);

async function act(work: () => Promise<Saved | unknown>) {
  busy.value = true;
  error.value = "";
  try {
    await work();
    saved.value = await mySaved();
    notes.value = await allNotes();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

// What a card's buttons do (Ray's round 5 list, item 6, 2026-11-15: "one
// button per tab over the two pills"). The page is in tabs by state, so the
// recipe page's two pills only repeated the tab here, and taking a recipe
// off the list meant pressing the pill that was already on, which nothing
// said. A card has the one move its tab leaves, "Cooked it" or "Cook
// again", and "Remove". None asks first: a line where the card was says
// what happened and offers Undo.
type List = (typeof lists.value)[number];
interface Done {
  list: string;
  owner?: string;
  recipe: SavedRecipe;
  was: State;
  // Where its card was among the tab's, and where it was in the whole list.
  at: number;
  whole: number;
  words: string;
}
const done = ref<Done | null>(null);
const said = ref("");
const page = ref<HTMLElement | null>(null);
// "About 8 seconds, or until the next action" (the same list).
const UNDO_MS = 8000;
let timer = 0;
let undoButton: HTMLButtonElement | null = null;
function hold(el: unknown) {
  undoButton = el as HTMLButtonElement | null;
}

// A tab's cards for one list, with the line where a card just was.
type Row = { recipe: SavedRecipe; done?: undefined } | { done: Done; recipe?: undefined };
function rows(l: List): Row[] {
  const cards: Row[] = of(l.recipes).map((recipe) => ({ recipe }));
  const d = done.value;
  if (d && d.list === l.key && d.was === tab.value) cards.splice(Math.min(d.at, cards.length), 0, { done: d });
  return cards;
}

// One request at a time, in the order they were asked for: Undo can be
// pressed before the change it undoes has been answered. The page changes
// first and isn't loaded again after, so the tabs' counts move at once; if
// the server says no, what it has is loaded and shown instead.
let sending: Promise<unknown> = Promise.resolve();
function send(work: () => Promise<unknown>) {
  sending = sending.then(work).catch(async (e) => {
    error.value = e instanceof Error ? e.message : String(e);
    // The line goes, and the card is back with what the server has: focus
    // that was on Undo goes to the card's own title.
    const d = done.value;
    const held = onUndo();
    clearTimeout(timer);
    done.value = null;
    saved.value = await mySaved().catch(() => saved.value);
    if (d && held) nextTick(() => (titleOf(d) ?? after(d))?.focus());
  });
}

const onUndo = () => !!undoButton && document.activeElement === undoButton;
// A card's title, where the card is there.
const titleOf = (d: Done) =>
  page.value?.querySelector<HTMLElement>(`[data-list="${d.list}"] [data-recipe="${d.recipe.id}"] h3 a`);
// The title of the card that came after it, the last card if none did, or
// the tab if the list has no cards left.
function after(d: Done) {
  const titles = page.value?.querySelectorAll<HTMLElement>(`[data-list="${d.list}"] .hit h3 a`);
  return (
    titles?.[Math.min(d.at, titles.length - 1)] ??
    page.value?.querySelector<HTMLElement>('.kind-filter [aria-pressed="true"]')
  );
}

function say(words: string) {
  // Emptied first, so the same words twice running are said twice.
  said.value = "";
  nextTick(() => (said.value = words));
}

// The line goes. If focus was on its Undo, it would be left on nothing, so
// it moves to the title of the card that came after, the last card if none
// did, or the tab if the list has no cards left. Focus that had already
// gone somewhere else is left there.
function clear() {
  const d = done.value;
  if (!d) return;
  clearTimeout(timer);
  const held = onUndo();
  done.value = null;
  if (held) nextTick(() => after(d)?.focus());
}

// Moves a recipe to the other tab, or with no state takes it off the list.
function change(l: List, r: SavedRecipe, to: State | null) {
  error.value = "";
  clearTimeout(timer);
  const was = r.state;
  const at = of(l.recipes).findIndex((x) => x.id === r.id);
  const whole = l.recipes.findIndex((x) => x.id === r.id);
  const words = to ? `Moved to ${to === "cooked" ? "Cooked" : "Want to cook"}.` : "Removed.";
  if (to) r.state = to;
  else l.recipes.splice(whole, 1);
  done.value = { list: l.key, owner: l.owner, recipe: { ...r, state: was }, was, at, whole, words };
  say(words);
  nextTick(() => undoButton?.focus());
  timer = window.setTimeout(clear, UNDO_MS);
  send(() => (to ? save(r.id, to, l.owner) : unsave(r.id, l.owner)));
}

// Puts it back as it was: the same tab and the same place, which is the
// list's order by source and title. What isn't the same is the date it was
// saved, when it had been removed; the page doesn't show one.
function undo() {
  const d = done.value;
  const l = lists.value.find((x) => x.key === d?.list);
  if (!d || !l) return;
  clearTimeout(timer);
  done.value = null;
  const now = l.recipes.find((x) => x.id === d.recipe.id);
  if (now) now.state = d.was;
  else l.recipes.splice(Math.min(d.whole, l.recipes.length), 0, d.recipe);
  say("Put back.");
  nextTick(() => titleOf(d)?.focus());
  send(() => save(d.recipe.id, d.was, d.owner));
}
onBeforeUnmount(() => clearTimeout(timer));

function toggleGroup(groupId: string, on: boolean) {
  const ids = new Set(saved.value!.shared_with.map((g) => g.id));
  if (on) ids.add(groupId);
  else ids.delete(groupId);
  act(() => shareSaved([...ids]));
}

watch(
  () => props.user,
  (user) => {
    if (user && !saved.value) act(async () => {});
  },
  { immediate: true },
);
</script>

<template>
  <article ref="page" class="wide saved-page">
    <div class="list-head">
      <h1>Saved recipes</h1>
      <p class="muted">
        The recipes you want to cook, the ones you have, and your notes. Only you see them, and the household
        <a href="/groups">groups</a> you share them with. To save one, open its page and choose
        “Want to cook”.
      </p>
    </div>
    <p v-if="user === null" class="status">
      <SignInLink /> to save recipes.
    </p>
    <template v-else-if="user">
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="!saved && !error" class="status">Loading…</p>
      <template v-else-if="saved">
        <div class="saved-tools">
          <div class="kind-filter" role="group" aria-label="Which recipes">
            <button type="button" class="secondary small" :aria-pressed="tab === 'want'" @click="tab = 'want'">
              Want to cook <span class="count">{{ count("want").toLocaleString() }}</span>
            </button>
            <button type="button" class="secondary small" :aria-pressed="tab === 'cooked'" @click="tab = 'cooked'">
              Cooked <span class="count">{{ count("cooked").toLocaleString() }}</span>
            </button>
            <button type="button" class="secondary small" :aria-pressed="tab === 'notes'" @click="tab = 'notes'">
              Notes <span class="count">{{ notes.length.toLocaleString() }}</span>
            </button>
          </div>
          <a v-if="every.length" href="/search?sv=1" class="secondary">Search my saved recipes</a>
        </div>
        <section v-if="tab === 'notes'" class="saved-section">
          <p v-if="!notes.length" class="status">
            No notes yet. On a recipe's page, “Add a note” keeps your own words about it: yours
            alone, unless you share it with a group.
          </p>
          <ul v-else class="hits">
            <li v-for="(n, i) in notes" :key="i" class="hit">
              <CoverThumb :src="n.cover_url" :title="n.source_title" />
              <div>
                <h3><a :href="`/recipes/${n.id}`">{{ n.title }}</a></h3>
                <p class="hit-where">
                  <a :href="`/sources/${n.source_id}`">{{ n.source_title }}</a
                  ><template v-if="whereItIs(n)"> · {{ whereItIs(n) }}</template>
                </p>
                <p class="saved-note">{{ n.body }}</p>
                <p class="hit-where">
                  {{ n.mine ? "Your note" : `${n.author ?? "Someone"}'s note` }} ·
                  {{ when(n.noted_at) }}
                </p>
              </div>
            </li>
          </ul>
        </section>
        <section v-for="l in tab === 'notes' ? [] : lists" :key="l.key" class="saved-section">
          <template v-if="l.owner">
            <h2>{{ l.title }}</h2>
            <p class="muted">{{ l.note }}</p>
          </template>
          <template v-else>
            <p v-if="saved.groups.length" class="saved-sharing">
              <span v-if="saved.shared_with.length && !sharing" class="muted"
                >Shared with {{ saved.shared_with.map((g) => g.name).join(", ") }}.</span
              >
              <button type="button" class="secondary small" :aria-expanded="sharing" @click="sharing = !sharing">
                Share
              </button>
            </p>
            <fieldset v-if="sharing" class="larder-share">
              <legend>Who else sees them</legend>
              <label v-for="g in saved.groups" :key="g.id" class="check">
                <input
                  type="checkbox"
                  :checked="saved.shared_with.some((x) => x.id === g.id)"
                  :disabled="busy"
                  @change="toggleGroup(g.id, ($event.target as HTMLInputElement).checked)"
                />
                {{ g.name }}
              </label>
              <p class="help">
                Its members see your saved recipes; editors and admins of the group change what's
                on the list.
              </p>
            </fieldset>
          </template>
          <p v-if="!rows(l).length" class="status">
            <template v-if="tab === 'want'">
              {{ l.owner ? "Nothing they want to cook yet." : "Nothing you want to cook yet." }}
              <template v-if="!l.owner"> <a href="/search">Search</a> for something.</template>
            </template>
            <template v-else>Nothing marked cooked yet.</template>
          </p>
          <ul v-else class="hits" :data-list="l.key">
            <template v-for="row in rows(l)" :key="row.done ? 'done' : row.recipe.id">
              <!-- Where a card just was: what happened to it, and Undo. -->
              <li v-if="row.done" class="hit done-line">
                <p>
                  {{ row.done.words }}
                  <button
                    :ref="hold"
                    type="button"
                    class="link"
                    :aria-label="`Undo: ${row.done.recipe.title}`"
                    @click="undo"
                  >
                    Undo
                  </button>
                </p>
              </li>
              <li v-else class="hit" :data-recipe="row.recipe.id">
                <CoverThumb :src="row.recipe.cover_url" :title="row.recipe.source_title" />
                <div>
                  <h3>
                    <a :href="`/recipes/${row.recipe.id}`">{{ row.recipe.title }}</a>
                  </h3>
                  <p class="hit-where">
                    <a :href="`/sources/${row.recipe.source_id}`">{{ row.recipe.source_title }}</a
                    ><template v-if="whereItIs(row.recipe)"> · {{ whereItIs(row.recipe) }}</template>
                  </p>
                  <!-- Plain buttons, not toggles: each does one thing and
                       its card goes. Named with the recipe, since a screen
                       reader may meet a button without its card. The icons
                       are the recipe page's pills' (PillToggle.vue). -->
                  <p v-if="l.editable" class="saved-actions">
                    <button
                      v-if="tab === 'want'"
                      type="button"
                      class="secondary small"
                      :aria-label="`Cooked it: ${row.recipe.title}`"
                      @click="change(l, row.recipe, 'cooked')"
                    >
                      <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10.5l4 4 8-9" /></svg>
                      Cooked it
                    </button>
                    <button
                      v-else
                      type="button"
                      class="secondary small"
                      :aria-label="`Cook again: ${row.recipe.title}`"
                      @click="change(l, row.recipe, 'want')"
                    >
                      <svg viewBox="0 0 16 20" aria-hidden="true" class="bookmark">
                        <path d="M3 2.5h10v15l-5-4-5 4z" />
                      </svg>
                      Cook again
                    </button>
                    <button
                      type="button"
                      class="link"
                      :aria-label="`Remove: ${row.recipe.title}`"
                      @click="change(l, row.recipe, null)"
                    >
                      Remove
                    </button>
                  </p>
                </div>
              </li>
            </template>
          </ul>
        </section>
        <p class="visually-hidden" aria-live="polite">{{ said }}</p>
      </template>
    </template>
  </article>
</template>

<style scoped>
.saved-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  margin-bottom: 1rem;
}
.saved-section + .saved-section {
  margin-top: 2rem;
}
.saved-sharing {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.75rem;
  margin: 0 0 0.75rem;
}
.saved-note {
  white-space: pre-line;
}
/* The tab's one move and "Remove", on one row on a phone too. */
.saved-actions {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 0.5rem;
}
.saved-actions .secondary {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  white-space: nowrap;
}
.saved-actions svg {
  flex: none;
  width: 1rem;
  height: 1rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.75;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.saved-actions svg.bookmark {
  width: 0.75rem;
}
/* "Remove" and "Undo" are words to press: drawn as text, and 44px to tap
   as the small button beside them is, by the same means. */
.saved-section button.link {
  position: relative;
  font-size: var(--text-sm);
}
.saved-section button.link::after {
  content: "";
  position: absolute;
  top: 50%;
  left: 50%;
  width: max(100%, 2.75rem);
  height: max(100%, 2.75rem);
  transform: translate(-50%, -50%);
}
.done-line {
  color: var(--muted);
}
</style>
