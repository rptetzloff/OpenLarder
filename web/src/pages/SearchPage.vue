<script setup lang="ts">
import { dropLastOn } from "../chips";
import CoverThumb from "../components/CoverThumb.vue";
import LarderPicker from "../components/LarderPicker.vue";
import OptionList from "../components/OptionList.vue";
import { KINDS, listTags, type Tag } from "../tags";
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { findBooks } from "../books";
import { type Example, findExamples } from "../examples";
import {
  listIngredients,
  type Named,
  type SearchResult,
  searchRecipes,
  whereItIs,
} from "../ingredients";

import type { Me } from "../me";
import { useNarrow } from "../narrow";

defineProps<{ user?: Me | null }>();
document.title = "Search · OpenLarder";

// What can I make from these sources with what I have? Ingredients you have
// rank the recipes (the more of a recipe you have, the higher); title words,
// sources and kinds of source narrow them. All of it is kept in the address
// (?i=…&q=…&source=…&kind=…&page=…), so a search can be bookmarked or shared.
//
// Laid out from Ray's round 4 wireframes, 2026-11-14 (part C of that list):
// one bar that stays, "Cook with what you have" under it, and the rest
// under "More options". The form had been a screen and more on a phone
// (about 1,000px) before any result, folded to a line once it had run.
// Nothing it could ask is gone, and a link made before opens the same search.
const MAX_INGREDIENTS = 30;
const MAX_SOURCES = 10;
// The wireframe's kinds of source, grouped as people think of them; the
// first three show, the rest behind "More kinds".
const KIND_GROUPS = [
  { label: "Books", kinds: ["book"] },
  { label: "Websites", kinds: ["website"] },
  { label: "Magazines and newspapers", kinds: ["magazine", "newspaper"] },
  { label: "TV, video and podcasts", kinds: ["tv_show", "video_channel", "podcast"] },
  { label: "Social media", kinds: ["social"] },
  { label: "Packaging", kinds: ["packaging"] },
  { label: "Family collections", kinds: ["family"] },
];
const ALL_KINDS = KIND_GROUPS.flatMap((g) => g.kinds);

const params = new URLSearchParams(location.search);
const chosen = ref<Named[]>([]);
// With what's in your larder (routers/larder.py), as well as ingredients
// chosen: the lists ticked, only some things in them, or all but some. An
// older link's larder=1 ticks every list.
const larderLists = ref<string[]>(params.getAll("ll"));
const larderOnly = ref<string[]>(params.getAll("li"));
const larderOut = ref<string[]>(params.getAll("lx"));
const larderAll = params.get("larder") === "1";
const useLarder = computed(() => !!larderLists.value.length || !!larderOnly.value.length);
// The lists there are, once the picker has them: "Use my larder" is for
// someone with one. Ticking it is every list, or those ticked before it was
// last unticked; which lists, and the rest, are under "More options".
const larderIds = ref<string[]>([]);
let listsBefore: string[] = [];
function toggleLarder(on: boolean) {
  if (on) larderLists.value = listsBefore.length ? listsBefore : [...larderIds.value];
  else {
    listsBefore = larderLists.value;
    larderLists.value = [];
    larderOnly.value = [];
  }
  run();
}
const larderNarrowed = computed(
  () =>
    useLarder.value &&
    (!!larderOnly.value.length ||
      !!larderOut.value.length ||
      (!!larderIds.value.length && larderLists.value.length < larderIds.value.length)),
);
function larderLoaded(ids: string[]) {
  larderIds.value = ids;
  // A link naming some of the lists and not all: that's an option in use.
  if (larderNarrowed.value) moreOpen.value = true;
}
// What you don't have or want (Ray, 2026-11-08): recipes needing one are left
// out; a line offering something else ("butter or oil") doesn't need it.
const unwanted = ref<Named[]>([]);
const shelf = ref<Named[]>([]);
// Only the books you own (routers/shelf.py).
const onShelf = ref(params.get("own") === "1");
// Only the recipes you've saved (routers/saved.py); enough to search by.
const onlySaved = ref(params.get("sv") === "1");
// The order: as they match (closest to made; for title words, the closest
// title; else by source and title), or the rated ones first, best first.
// Ray, 2026-11-12.
const sort = ref<"match" | "rating">(params.get("sort") === "rating" ? "rating" : "match");
// Only what you can make (Ray, 2026-11-14): with ingredients or a larder,
// keep the recipes missing nothing, or a line or two (missing=0, 1 or 2 in
// the address). Without it they rank recipes and never filter them. The
// choice offers 0 and 2; a link's 1 is offered while it's the one chosen.
const asMissing = params.get("missing") ?? "";
const missingMax = ref<number | null>(["0", "1", "2"].includes(asMissing) ? Number(asMissing) : null);
const SHOWN = ["Can make now", "Missing 1 or fewer", "Missing 2 or fewer"];
const show = computed({
  get: () => (missingMax.value === null ? "" : String(missingMax.value)),
  set: (to: string) => (missingMax.value = to === "" ? null : Number(to)),
});
const title = ref(params.get("q") ?? "");
// Every kind until some are unticked; the address lists them only then.
const asked = params.getAll("kind").filter((k) => ALL_KINDS.includes(k));
const kinds = ref<string[]>(asked.length ? asked : [...ALL_KINDS]);
const page = ref(Math.max(1, Number(params.get("page")) || 1));
// Recipes with every tag ticked. Diet and course are open beside the
// results; cuisine and technique, and the kinds of source, are closed until
// opened or something in them is ticked.
const allTags = ref<Tag[]>([]);
const tags = ref<string[]>(params.getAll("tag"));
const open = reactive({ diet: true, course: true, kinds: asked.length > 0, more: false });
// Diets: the first six, the rest behind "Show all diets" (Ray's cleanup
// pass, section 5), unless one of the rest is ticked.
const DIETS_SHOWN = 6;
const allDiets = ref(false);
const tagsOf = (kind: string) => allTags.value.filter((t) => t.kind === kind);
const diets = computed(() => {
  const all = tagsOf("diet");
  const folded =
    !allDiets.value &&
    all.length > DIETS_SHOWN &&
    !all.slice(DIETS_SHOWN).some((t) => tags.value.includes(t.id));
  return { tags: folded ? all.slice(0, DIETS_SHOWN) : all, more: all.length > DIETS_SHOWN, folded };
});
const others = computed(() =>
  KINDS.filter((k) => k.kind === "cuisine" || k.kind === "technique")
    .map((k) => ({ ...k, tags: tagsOf(k.kind) }))
    .filter((k) => k.tags.length),
);
const result = ref<SearchResult | null>(null);
const missing = ref(0);
const failed = ref(false);
const loading = ref(false);
let latest = 0;

// On a phone the filters are inside "More options", in the document itself
// (Teleport), so there is one button above the results and Tab and a screen
// reader meet the filters where they're seen. *Ray, 2026-11-15: "Filters
// probably makes sense under More options".* There had been a second
// button, "Filters", which showed before any search, with nothing to
// filter. On a wide screen they stay the rail beside the results.
const narrow = useNarrow();
// The rest of what can be asked, closed until it's wanted, or a link
// arrives with some of it set (on a phone, a filter too); the button says
// how many are in use.
const moreOpen = ref(
  ["x", "source", "book", "own", "sv", "li", "lx"].some((k) => params.has(k)) ||
    (narrow.value && ["tag", "kind"].some((k) => params.has(k))),
);
const moreCount = computed(
  () =>
    [
      unwanted.value.length,
      shelf.value.length,
      onShelf.value,
      onlySaved.value,
      larderNarrowed.value,
    ].filter(Boolean).length,
);
// Ingredients of yours to count against a recipe's lines: chosen, on their
// way from the address, or a larder's.
const arriving = ref(params.has("i"));
const ranked = computed(() => !!chosen.value.length || useLarder.value || arriving.value);
// How many filters are narrowing the search; on a phone, where they are
// in the panel, the button counts them with the options.
const activeFilters = computed(() => tags.value.length + (narrowedKinds.value.length ? 1 : 0));
const inPanel = computed(() => moreCount.value + (narrow.value ? activeFilters.value : 0));
// The results' heading takes focus after a search someone asked for, and
// the count is said; a search that follows typing leaves focus alone.
const resultsHead = ref<HTMLElement | null>(null);
const said = ref("");
async function toResults() {
  await nextTick();
  resultsHead.value?.focus();
}
async function submit() {
  await run();
  toResults();
}

const narrowedKinds = computed(() =>
  kinds.value.length === ALL_KINDS.length ? [] : kinds.value,
);
// What's narrowing the results, each to take off by itself, and all at
// once. What's searched for (title words, what you have) isn't among them.
const tagName = (id: string) =>
  (allTags.value.find((t) => t.id === id) ?? result.value?.tags.find((t) => t.id === id))?.name ??
  "A tag";
const narrowing = computed(() => {
  const chips: { key: string; label: string; remove: () => void }[] = [];
  const add = (key: string, label: string, remove: () => void) => chips.push({ key, label, remove });
  if (missingMax.value !== null && ranked.value)
    add("missing", SHOWN[missingMax.value], () => (missingMax.value = null));
  for (const id of tags.value) add(`tag-${id}`, tagName(id), () => toggleTag(id, false));
  if (narrowedKinds.value.length) {
    const whole = KIND_GROUPS.filter((g) => groupTicked(g.kinds)).map((g) => g.label);
    add("kinds", whole.join(", ") || "Some kinds of source", () => (kinds.value = [...ALL_KINDS]));
  }
  if (onShelf.value) add("shelf", "On my shelf", () => (onShelf.value = false));
  if (onlySaved.value) add("saved", "Saved", () => (onlySaved.value = false));
  for (const i of unwanted.value) add(`x-${i.id}`, `Without ${i.name}`, () => dropUnwanted(i.id, false));
  for (const b of shelf.value) add(`in-${b.id}`, `In ${b.name}`, () => dropSource(b.id, false));
  return chips;
});
// The chip pressed is gone: focus goes to the one now in its place, or
// with none left, to the results.
const chipRow = ref<HTMLElement | null>(null);
async function takeOff(n: number) {
  narrowing.value[n].remove();
  await nextTick();
  const left = chipRow.value?.querySelectorAll<HTMLButtonElement>("button.filter-chip") ?? [];
  if (left.length) left[Math.min(n, left.length - 1)].focus();
  else resultsHead.value?.focus();
}
function clearAll() {
  missingMax.value = null;
  tags.value = [];
  kinds.value = [...ALL_KINDS];
  onShelf.value = false;
  onlySaved.value = false;
  unwanted.value = [];
  shelf.value = [];
  run();
  toResults();
}
// From an empty "only what I can make now": the next step, in one press.
function widen() {
  missingMax.value = missingMax.value === 2 ? null : 2;
  toResults();
}

const searching = computed(
  () =>
    useLarder.value ||
    onlySaved.value ||
    !!chosen.value.length ||
    !!title.value.trim() ||
    !!tags.value.length,
);

function toAddress() {
  const url = new URL(location.href);
  for (const key of ["i", "x", "book", "source", "q", "kind", "tag", "page", "larder", "ll", "li", "lx", "own", "sv", "sort", "missing"]) {
    url.searchParams.delete(key);
  }
  if (sort.value === "rating") url.searchParams.set("sort", "rating");
  if (missingMax.value !== null && ranked.value) url.searchParams.set("missing", String(missingMax.value));
  for (const i of unwanted.value) url.searchParams.append("x", i.id);
  for (const b of shelf.value) url.searchParams.append("source", b.id);
  for (const i of chosen.value) url.searchParams.append("i", i.id);
  if (title.value.trim()) url.searchParams.set("q", title.value.trim());
  for (const k of narrowedKinds.value) url.searchParams.append("kind", k);
  for (const t of tags.value) url.searchParams.append("tag", t);
  if (page.value > 1) url.searchParams.set("page", String(page.value));
  for (const id of larderLists.value) url.searchParams.append("ll", id);
  for (const id of larderOnly.value) url.searchParams.append("li", id);
  for (const id of larderOut.value) url.searchParams.append("lx", id);
  if (onShelf.value) url.searchParams.set("own", "1");
  if (onlySaved.value) url.searchParams.set("sv", "1");
  history.replaceState(null, "", url);
}

async function run(toPage = 1) {
  const mine = ++latest;
  page.value = toPage;
  toAddress();
  failed.value = false;
  if (!searching.value) {
    result.value = null;
    return;
  }
  loading.value = true;
  try {
    const perPage = result.value?.per_page ?? 0;
    const found = await searchRecipes(
      chosen.value.map((i) => i.id),
      {
        offset: perPage ? (toPage - 1) * perPage : 0,
        sources: shelf.value.map((b) => b.id),
        q: title.value,
        kinds: narrowedKinds.value,
        without: unwanted.value.map((i) => i.id),
        tags: tags.value,
        larder: useLarder.value,
        larderLists: larderLists.value,
        larderItems: larderOnly.value,
        larderWithout: larderOut.value,
        onShelf: onShelf.value,
        saved: onlySaved.value,
        byRating: sort.value === "rating",
        missingMax: missingMax.value,
      },
    );
    if (mine !== latest) return;
    result.value = found;
    said.value = summary.value;
  } catch {
    if (mine === latest) failed.value = true;
  } finally {
    if (mine === latest) loading.value = false;
  }
}

let titleTimer: ReturnType<typeof setTimeout> | undefined;
watch(title, () => {
  clearTimeout(titleTimer);
  titleTimer = setTimeout(() => run(), 300);
});
watch(kinds, () => run(), { deep: true });
watch(onShelf, () => run());
watch(onlySaved, () => run());
watch(sort, () => run());
watch(missingMax, () => run());
// With nothing of yours left to count, there's nothing to be missing.
watch(ranked, (now) => {
  if (!now) missingMax.value = null;
});
watch(tags, () => run(), { deep: true });
function toggleTag(id: string, on: boolean) {
  tags.value = on ? [...tags.value, id] : tags.value.filter((t) => t !== id);
}

// Type-to-find, for sources and for ingredients: suggestions from the
// server, leaving out what's already chosen.
function finder<T extends Named>(find: (q: string) => Promise<T[]>, taken: () => Named[]) {
  const query = ref("");
  const suggestions = ref<T[]>([]);
  let typed = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  watch(query, () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const mine = ++typed;
      const q = query.value.trim();
      const found = q ? await find(q).catch(() => null) : [];
      if (mine !== typed || !found) return;
      const ids = new Set(taken().map((t) => t.id));
      suggestions.value = found.filter((t) => !ids.has(t.id)).slice(0, 8);
    }, 200);
  });
  return { query, suggestions };
}

const unwantedFind = finder(
  async (q) => (await listIngredients(q)).ingredients,
  () => [...unwanted.value, ...chosen.value],
);
function addUnwanted(item: Named) {
  if (unwanted.value.length < MAX_INGREDIENTS) unwanted.value.push({ id: item.id, name: item.name });
  unwantedFind.query.value = "";
  unwantedFind.suggestions.value = [];
  document.getElementById("search-unwanted")?.focus();
  run();
}
function dropUnwanted(id: string, refocus = true) {
  unwanted.value = unwanted.value.filter((i) => i.id !== id);
  if (refocus) document.getElementById("search-unwanted")?.focus();
  run();
}

const ingredientFind = finder(
  async (q) => (await listIngredients(q)).ingredients,
  () => [...chosen.value, ...unwanted.value],
);
const sourceFind = finder(
  async (q) => (await findBooks(q)).map((b) => ({ ...b, name: b.title })),
  () => shelf.value,
);

function addIngredient(item: Named) {
  if (chosen.value.length < MAX_INGREDIENTS) chosen.value.push({ id: item.id, name: item.name });
  ingredientFind.query.value = "";
  ingredientFind.suggestions.value = [];
  document.getElementById("search-ingredient")?.focus();
  run();
}
function addSource(item: Named) {
  if (shelf.value.length < MAX_SOURCES) shelf.value.push({ id: item.id, name: item.name });
  sourceFind.query.value = "";
  sourceFind.suggestions.value = [];
  document.getElementById("search-source")?.focus();
  run();
}
function dropIngredient(id: string) {
  chosen.value = chosen.value.filter((i) => i.id !== id);
  document.getElementById("search-ingredient")?.focus();
  run();
}
function dropSource(id: string, refocus = true) {
  shelf.value = shelf.value.filter((b) => b.id !== id);
  if (refocus) document.getElementById("search-source")?.focus();
  run();
}

// A group is ticked when every kind in it is.
const groupTicked = (kindsInGroup: string[]) => kindsInGroup.every((k) => kinds.value.includes(k));
function toggleGroup(kindsInGroup: string[], on: boolean) {
  const rest = kinds.value.filter((k) => !kindsInGroup.includes(k));
  kinds.value = on ? [...rest, ...kindsInGroup] : rest;
}

// What the button says after a try: copied, or where to copy it from.
const copyNote = ref("");
async function copyLink() {
  toAddress();
  try {
    await navigator.clipboard.writeText(location.href);
    copyNote.value = "Link copied";
  } catch {
    copyNote.value = "Couldn't copy: the address bar has the link";
  }
  setTimeout(() => (copyNote.value = ""), 4000);
}

const pages = computed(() => {
  const r = result.value;
  return r && r.per_page ? Math.max(1, Math.ceil(r.total / r.per_page)) : 1;
});
// Page numbers to offer: the first, the last, and those near this one.
const pageLinks = computed(() => {
  const near = new Set([1, pages.value, page.value - 1, page.value, page.value + 1]);
  const list = [...near].filter((n) => n >= 1 && n <= pages.value).sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  for (const n of list) {
    if (out.length && typeof out[out.length - 1] === "number" && n - (out[out.length - 1] as number) > 1)
      out.push("…");
    out.push(n);
  }
  return out;
});
function goTo(n: number) {
  run(n);
  document.getElementById("results-top")?.scrollIntoView();
}

// "Onion", "Onion and Frog's Legs", "Onion, Garlic and Frog's Legs".
function inWords(names: string[]) {
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : (names[0] ?? "");
}

const summary = computed(() => {
  const r = result.value;
  if (!r) return "";
  const found = `${r.total.toLocaleString()} ${r.total === 1 ? "recipe" : "recipes"}`;
  if (missingMax.value === null || !ranked.value) return found;
  return missingMax.value ? `${found} missing ${missingMax.value} or fewer` : `${found} you can make now`;
});

// Finished searches to try, before anything is asked (examples.ts).
const examples = ref<Example[]>([]);

onMounted(async () => {
  listTags()
    .then((found) => {
      allTags.value = found;
      // A tag in the link that's in the closed kinds: open them.
      if (found.some((t) => tags.value.includes(t.id) && !["diet", "course"].includes(t.kind))) {
        open.more = true;
      }
    })
    .catch(() => {});
  const ids = params.getAll("i").slice(0, MAX_INGREDIENTS);
  const sources = [...params.getAll("source"), ...params.getAll("book")].slice(0, MAX_SOURCES);
  if (!searching.value && !ids.length) findExamples().then((found) => (examples.value = found));
  try {
    if (
      !ids.length &&
      !title.value.trim() &&
      !tags.value.length &&
      !useLarder.value &&
      !onlySaved.value
    ) {
      // larder=1 alone: the picker ticks every list, then searches.
      // Sources, before anything to search by: their names are all to show.
      for (const id of sources) {
        const res = await fetch(`/api/sources/${id}`);
        if (res.ok) shelf.value.push({ id, name: (await res.json()).title });
      }
      const leftOut = params.getAll("x").slice(0, MAX_INGREDIENTS);
      for (const id of leftOut) {
        const res = await fetch(`/api/ingredients/${id}`);
        if (res.ok) unwanted.value.push({ id, name: (await res.json()).name });
      }
      if (shelf.value.length < sources.length || unwanted.value.length < leftOut.length) toAddress();
      return;
    }
    // The search names the ingredients and sources, so a link needs only IDs.
    const first = await searchRecipes(ids, {
      sources,
      q: title.value,
      kinds: narrowedKinds.value,
      without: params.getAll("x").slice(0, MAX_INGREDIENTS),
      tags: tags.value,
      larder: useLarder.value,
      larderLists: larderLists.value,
      larderItems: larderOnly.value,
      larderWithout: larderOut.value,
      onShelf: onShelf.value,
      saved: onlySaved.value,
      byRating: sort.value === "rating",
      missingMax: missingMax.value,
    });
    chosen.value = first.ingredients;
    unwanted.value = first.without;
    shelf.value = first.sources;
    missing.value =
      first.missing.length + first.missing_sources.length + first.missing_tags.length;
    if (first.missing_tags.length) {
      tags.value = tags.value.filter((t) => !first.missing_tags.includes(t));
    }
    result.value = first;
    said.value = summary.value;
    if (missing.value || page.value > 1) run(page.value);
    else toResults();
  } catch {
    failed.value = true;
  } finally {
    arriving.value = false;
  }
});
</script>

<template>
  <article class="wide search-page">
    <!-- The bar says what the page is; the heading is for whoever goes by headings. -->
    <h1 class="visually-hidden">Search</h1>

    <form id="search-form" class="search-form" role="search" @submit.prevent="submit">
      <div class="search-bar">
        <label for="search-title" class="visually-hidden">Search recipe titles</label>
        <input
          id="search-title"
          v-model="title"
          type="search"
          autocomplete="off"
          maxlength="200"
          placeholder="Search recipe titles"
        />
        <button type="submit" class="primary">Search</button>
      </div>

      <label for="search-ingredient">Cook with what you have</label>
      <div class="have-row">
        <div class="have-box">
          <div class="chip-input" @click="($event.currentTarget as HTMLElement).querySelector('input')?.focus()">
            <span v-for="i in chosen" :key="i.id" class="chip">
              {{ i.name }}
              <button type="button" class="remove" :aria-label="`Remove ${i.name}`" @click.stop="dropIngredient(i.id)">
                ×
              </button>
            </span>
            <input
              id="search-ingredient"
              v-model="ingredientFind.query.value"
              type="search"
              autocomplete="off"
              :placeholder="chosen.length ? 'Add another' : 'Add an ingredient'"
              aria-describedby="search-ingredient-help"
              :disabled="chosen.length >= MAX_INGREDIENTS"
              @keydown="dropLastOn($event, chosen, (i) => dropIngredient(i.id))"
              @keydown.enter.prevent="
                ingredientFind.suggestions.value[0] && addIngredient(ingredientFind.suggestions.value[0])
              "
            />
          </div>
          <OptionList
            v-slot="{ option: s }"
            :options="ingredientFind.suggestions.value"
            for="search-ingredient"
            @pick="addIngredient"
          >
            {{ s.name }}
            <span class="page-ref">
              {{ s.recipes.toLocaleString() }} {{ s.recipes === 1 ? "recipe" : "recipes" }}
            </span>
          </OptionList>
        </div>
        <label v-if="user && (larderIds.length || useLarder)" class="check use-larder">
          <input
            type="checkbox"
            :checked="useLarder"
            @change="toggleLarder(($event.target as HTMLInputElement).checked)"
          />
          Use my larder
        </label>
      </div>
      <!-- Said to a screen reader with the box; shown while the box is in use. -->
      <p id="search-ingredient-help" class="help when-adding">
        Up to {{ MAX_INGREDIENTS }}. An ingredient also finds what counts as it: cheese finds
        cheddar.
      </p>

      <div v-if="ranked" class="show-row">
        <label for="search-show">Show</label>
        <select id="search-show" v-model="show">
          <option value="">Anything using these</option>
          <option v-if="missingMax === 1" value="1">Missing 1 or fewer</option>
          <option value="2">Missing 2 or fewer</option>
          <option value="0">Only what I can make now</option>
        </select>
      </div>

      <button
        type="button"
        class="link more-toggle"
        :aria-expanded="moreOpen"
        aria-controls="search-more"
        @click="moreOpen = !moreOpen"
      >
        More options{{ inPanel ? ` (${inPanel})` : "" }}
        <svg viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4" /></svg>
      </button>
      <div v-show="moreOpen" id="search-more" class="more-panel">
        <label for="search-unwanted">Leave out ingredients</label>
        <div class="chip-input" @click="($event.currentTarget as HTMLElement).querySelector('input')?.focus()">
          <span v-for="i in unwanted" :key="i.id" class="chip chip-unwanted">
            {{ i.name }}
            <button type="button" class="remove" :aria-label="`Remove ${i.name}`" @click.stop="dropUnwanted(i.id)">
              ×
            </button>
          </span>
          <input
            id="search-unwanted"
            v-model="unwantedFind.query.value"
            type="search"
            autocomplete="off"
            placeholder="Add an ingredient to leave out"
            aria-describedby="search-unwanted-help"
            :disabled="unwanted.length >= MAX_INGREDIENTS"
            @keydown="dropLastOn($event, unwanted, (i) => dropUnwanted(i.id))"
            @keydown.enter.prevent="
              unwantedFind.suggestions.value[0] && addUnwanted(unwantedFind.suggestions.value[0])
            "
          />
        </div>
        <OptionList
          v-slot="{ option: s }"
          :options="unwantedFind.suggestions.value"
          for="search-unwanted"
          @pick="addUnwanted"
        >
          {{ s.name }}
          <span class="page-ref">
            {{ s.recipes.toLocaleString() }} {{ s.recipes === 1 ? "recipe" : "recipes" }}
          </span>
        </OptionList>
        <p id="search-unwanted-help" class="help">
          Recipes that need one are left out. One that offers another choice, like “butter or oil”,
          stays.
        </p>

        <label for="search-source" class="more-gap">In sources</label>
        <div class="chip-input" @click="($event.currentTarget as HTMLElement).querySelector('input')?.focus()">
          <span v-for="b in shelf" :key="b.id" class="chip">
            {{ b.name }}
            <button type="button" class="remove" :aria-label="`Remove ${b.name}`" @click.stop="dropSource(b.id)">
              ×
            </button>
          </span>
          <input
            id="search-source"
            v-model="sourceFind.query.value"
            type="search"
            autocomplete="off"
            placeholder="Title, author or site"
            :disabled="shelf.length >= MAX_SOURCES"
            @keydown="dropLastOn($event, shelf, (b) => dropSource(b.id))"
            @keydown.enter.prevent="
              sourceFind.suggestions.value[0] && addSource(sourceFind.suggestions.value[0])
            "
          />
        </div>
        <OptionList
          v-slot="{ option: b }"
          :options="sourceFind.suggestions.value"
          for="search-source"
          @pick="addSource"
        >
          {{ b.title }}
          <span v-if="b.authors.length" class="page-ref">{{ b.authors.join(", ") }}</span>
        </OptionList>

        <template v-if="user">
          <label class="check more-gap">
            <input v-model="onShelf" type="checkbox" />
            Only books on <a href="/shelf">my shelf</a
            ><template v-if="onShelf && result?.shelf_books != null">
              ({{ result.shelf_books.toLocaleString() }}
              {{ result.shelf_books === 1 ? "book" : "books" }})</template
            >
          </label>
          <label class="check">
            <input v-model="onlySaved" type="checkbox" />
            Only recipes I've <a href="/saved">saved</a>
          </label>
          <LarderPicker
            v-model:lists="larderLists"
            v-model:only="larderOnly"
            v-model:leave-out="larderOut"
            :counted="result?.larder_items"
            :tick-all="larderAll"
            @change="run()"
            @loaded="larderLoaded"
          />
        </template>
        <!-- Where the filters go on a phone, after the options. -->
        <h2 v-if="narrow" class="more-filters-title">Filters</h2>
        <div id="more-filters"></div>
      </div>

      <p v-if="!searching && examples.length" class="try">
        <span class="muted">Try:</span>
        <!-- Named by what it does and the words on it, as on the front page. -->
        <a v-for="e in examples" :key="e.href" :href="e.href"
          ><span class="visually-hidden">Search for recipes using </span
          ><span class="chip">{{ e.label }}</span></a
        >
      </p>
    </form>

    <p v-if="missing" class="status">
      {{ missing === 1 ? "Something" : `${missing} things` }} in this link no longer
      {{ missing === 1 ? "exists" : "exist" }}, perhaps merged into another, so the search is
      without {{ missing === 1 ? "it" : "them" }}.
    </p>

    <div v-if="narrowing.length" ref="chipRow" class="narrowing" role="group" aria-label="Filters in use">
      <button
        v-for="(c, n) in narrowing"
        :key="c.key"
        type="button"
        class="filter-chip"
        :aria-label="`Remove filter: ${c.label}`"
        @click="takeOff(n)"
      >
        {{ c.label }}
        <svg viewBox="0 0 10 10" aria-hidden="true"><path d="M1 1l8 8M9 1l-8 8" /></svg>
      </button>
      <button type="button" class="link clear-all" @click="clearAll">Clear all</button>
    </div>

    <div class="search-body">
      <!-- The count, then what orders and narrows the list; in that order
           for a keyboard too, with the filters beside the list on a wide
           screen and folded under their button on a phone. -->
      <div id="results-top" class="results-top">
        <div v-if="searching && result && !failed" class="results-count">
          <h2 ref="resultsHead" class="results-head" tabindex="-1">
            {{ summary }}
            <span v-if="sort === 'rating'" class="muted order-note"> · highest rated first</span>
            <span
              v-else-if="(chosen.length || useLarder) && missingMax !== 0 && result.total > 1"
              class="muted order-note"
            >
              · closest to made first</span
            >
          </h2>
          <button type="button" class="link copy-link" @click="copyLink">Copy link</button>
          <span class="status" role="status">{{ copyNote }}</span>
        </div>
        <div class="results-controls">
          <template v-if="searching && result && !failed && result.total > 1">
            <label for="search-sort" class="visually-hidden">Sort</label>
            <select id="search-sort" v-model="sort">
              <option value="match">Best match</option>
              <option value="rating">Highest rated</option>
            </select>
          </template>
        </div>
      </div>

      <!-- A landmark of its own beside the results; on a phone, part of
           the panel, and not one. -->
      <Teleport to="#more-filters" :disabled="!narrow" defer>
      <component :is="narrow ? 'div' : 'aside'" class="filters" :aria-label="narrow ? undefined : 'Filters'">
        <div class="filters-body">
          <details
            v-if="diets.tags.length"
            :open="open.diet"
            @toggle="open.diet = ($event.target as HTMLDetailsElement).open"
          >
            <summary>Diet</summary>
            <div role="group" aria-label="Diet">
              <label v-for="t in diets.tags" :key="t.id" class="check">
                <input
                  type="checkbox"
                  :checked="tags.includes(t.id)"
                  @change="toggleTag(t.id, ($event.target as HTMLInputElement).checked)"
                />
                {{ t.name }}
              </label>
              <button
                v-if="diets.more"
                type="button"
                class="link"
                :aria-expanded="!diets.folded"
                @click="allDiets = !allDiets"
              >
                {{ diets.folded ? "Show all diets" : "Fewer diets" }}
              </button>
            </div>
          </details>
          <details
            v-if="tagsOf('course').length"
            :open="open.course"
            @toggle="open.course = ($event.target as HTMLDetailsElement).open"
          >
            <summary>Course</summary>
            <div role="group" aria-label="Course">
              <label v-for="t in tagsOf('course')" :key="t.id" class="check">
                <input
                  type="checkbox"
                  :checked="tags.includes(t.id)"
                  @change="toggleTag(t.id, ($event.target as HTMLInputElement).checked)"
                />
                {{ t.name }}
              </label>
            </div>
          </details>
          <details :open="open.kinds" @toggle="open.kinds = ($event.target as HTMLDetailsElement).open">
            <summary>Source kind</summary>
            <div role="group" aria-label="Source kind">
              <label v-for="g in KIND_GROUPS" :key="g.label" class="check">
                <input
                  type="checkbox"
                  :checked="groupTicked(g.kinds)"
                  @change="toggleGroup(g.kinds, ($event.target as HTMLInputElement).checked)"
                />
                {{ g.label }}
              </label>
            </div>
          </details>
          <details
            v-if="others.length"
            :open="open.more"
            @toggle="open.more = ($event.target as HTMLDetailsElement).open"
          >
            <summary>Cuisine and technique</summary>
            <div v-for="g in others" :key="g.kind" role="group" :aria-label="g.label">
              <p class="group-name" aria-hidden="true">{{ g.label }}</p>
              <label v-for="t in g.tags" :key="t.id" class="check">
                <input
                  type="checkbox"
                  :checked="tags.includes(t.id)"
                  @change="toggleTag(t.id, ($event.target as HTMLInputElement).checked)"
                />
                {{ t.name }}
              </label>
            </div>
          </details>
        </div>
      </component>
      </Teleport>

      <section id="results" class="results" :aria-busy="loading">
        <!-- The count, said once a search has run; not the whole list. -->
        <p class="visually-hidden" aria-live="polite">{{ said }}</p>
        <p v-if="failed" role="alert">The search didn't work. Try again.</p>
        <p v-else-if="!searching" class="status">
          Add what you have, words of a title or a tag, and the recipes you're closest to making
          come first, with where to find them.
        </p>
        <template v-else-if="result">
          <p v-if="result.shelf_books === 0" class="status">
            Your shelf has no books yet: on a book's page, “I have this book” puts it there.
          </p>
          <div v-else-if="result.total === 0 && missingMax !== null && ranked" class="nothing">
            <p class="status">
              {{
                missingMax === 0
                  ? "Nothing uses only what you have."
                  : `No recipe is missing ${missingMax} or fewer.`
              }}
            </p>
            <button type="button" class="secondary" @click="widen">
              {{ missingMax === 2 ? "Show anything using these" : "Show recipes missing 2 or fewer" }}
            </button>
          </div>
          <p v-else-if="result.total === 0" class="status">
            Nothing matched. If the book isn't indexed yet, <a href="/requests">request it</a>.
          </p>
          <ul class="hits">
            <li v-for="r in result.recipes" :key="r.id" class="hit">
              <CoverThumb :src="r.cover_url" :title="r.source_title" />
              <div>
                <h3><a :href="`/recipes/${r.id}`">{{ r.title }}</a></h3>
                <p class="hit-where">
                  <a :href="`/sources/${r.source_id}`">{{ r.source_title }}</a
                  ><template v-if="whereItIs(r)"> · {{ whereItIs(r) }}</template>
                </p>
                <template v-if="r.lines !== null">
                  <!-- Kept to what you can make: what's missing is the thing to say. -->
                  <template v-if="missingMax === null">
                    <p class="hit-have">Uses your {{ inWords(r.uses) }}</p>
                    <p class="hit-needs">
                      {{ r.needs.length ? `Still needs: ${r.needs.join(", ")}` : "Nothing else on its list" }}
                    </p>
                  </template>
                  <p v-else-if="r.needs.length" class="hit-needs">Missing: {{ r.needs.join(", ") }}</p>
                  <p v-else class="hit-have"><span aria-hidden="true">✓ </span>You have everything</p>
                </template>
              </div>
            </li>
          </ul>
          <nav v-if="pages > 1" class="pager" aria-label="Pages of results">
            <button v-if="page > 1" type="button" class="secondary" @click="goTo(page - 1)">
              Previous
            </button>
            <template v-for="(n, k) in pageLinks" :key="k">
              <span v-if="n === '…'" class="muted">…</span>
              <button
                v-else
                type="button"
                class="secondary"
                :aria-current="n === page ? 'page' : undefined"
                @click="goTo(n)"
              >
                {{ n }}
              </button>
            </template>
            <button v-if="page < pages" type="button" class="secondary" @click="goTo(page + 1)">
              Next
            </button>
          </nav>
        </template>
      </section>
    </div>
  </article>
</template>

<style scoped>
/* The form: one bar that stays, what you have under it, and the rest under
   "More options" (Ray's round 4 wireframes, 2026-11-14). */
.search-form {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.search-form > label,
.more-panel > label:not(.check) {
  font-weight: 600;
  font-size: 0.9375rem;
}
.search-bar {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.search-bar input {
  flex: 1;
  min-width: 0;
  min-height: 2.75rem;
  box-sizing: border-box;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  font: inherit;
}
/* The larder's tick beside the box while there's room, under it when not. */
.have-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 0 1rem;
}
.have-box {
  flex: 1 1 9rem;
  min-width: 0;
}
.have-box .chip-input {
  min-height: 2.75rem;
  box-sizing: border-box;
}
.use-larder {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  min-height: 2.75rem;
  white-space: nowrap;
}
.help,
.more-panel :deep(.help) {
  margin: 0;
  color: var(--muted);
  font-size: 0.875rem;
}
/* How the box works is for whoever is using it: two lines on a phone that
   the empty form doesn't spend otherwise. */
.when-adding {
  display: none;
}
.have-row:focus-within + .when-adding {
  display: block;
}
.show-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.375rem;
}
.show-row select,
.results-controls select {
  min-height: 2.75rem;
  max-width: 100%;
}
.show-row select {
  min-width: 0;
  padding: 0.375rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  font: inherit;
}
.more-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  align-self: flex-start;
  min-height: 2.75rem;
  font-weight: 600;
}
.more-toggle svg {
  width: 0.625rem;
  height: 0.375rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.more-toggle[aria-expanded="true"] svg {
  transform: rotate(180deg);
}
.more-panel {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  max-width: 44rem;
  padding: 1rem 1.25rem 0.5rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.more-panel .more-gap {
  margin-top: 0.75rem;
}
.more-panel :deep(.larder-picker) {
  margin: 0.75rem 0 0.5rem;
}
/* The example searches, as on the front page: each 44px to tap. */
.try {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0 0.5rem;
  margin: 0.25rem 0 0;
  font-size: var(--text-sm);
}
.try a {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  color: var(--fg);
  text-decoration: none;
}
.try .chip {
  padding: 0.125rem 0.625rem;
  border-radius: 999px;
  background: var(--chip);
}
.try a:hover .chip,
.try a:focus-visible .chip {
  text-decoration: underline;
}

/* What's narrowing the results: each a button that takes itself off, drawn
   as a chip and 44px to tap, in rows that far apart. */
.narrowing {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.8125rem 0.5rem;
  margin: 1rem 0 0;
}
.filter-chip {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  max-width: 100%;
  padding: 0.25rem 0.625rem;
  border: 0;
  border-radius: 6px;
  background: var(--chip);
  color: var(--fg);
  font: inherit;
  font-size: 0.9375rem;
  text-align: left;
  cursor: pointer;
}
.filter-chip::after {
  content: "";
  position: absolute;
  inset: 50% 0 auto;
  height: 2.75rem;
  transform: translateY(-50%);
}
.filter-chip:hover {
  text-decoration: underline;
}
.filter-chip svg {
  flex: none;
  width: 0.5625rem;
  height: 0.5625rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linecap: round;
}
.clear-all {
  min-height: 2.75rem;
  margin: -0.5rem 0 -0.5rem 0.25rem;
}

/* Beside the results: each kind of filter opens and closes by itself. */
.filters details {
  border-top: 1px solid var(--line);
}
.filters details:first-child {
  border-top: 0;
}
.filters summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 2.75rem;
  color: var(--muted);
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  cursor: pointer;
  list-style: none;
}
.filters summary::-webkit-details-marker {
  display: none;
}
.filters summary::after {
  content: "";
  width: 0.375rem;
  height: 0.375rem;
  margin-right: 0.25rem;
  border: solid currentColor;
  border-width: 0 1.5px 1.5px 0;
  transform: rotate(45deg);
}
.filters details[open] > summary::after {
  transform: rotate(-135deg);
}
.filters [role="group"] {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
  padding-bottom: 0.875rem;
}
.filters .group-name {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
}

.results-head:focus {
  outline: none;
}
.filters .check {
  font-weight: normal;
}
/* The filters beside the list, with the count and the controls over the
   list; on a phone one column: count, controls, filters, list. */
.search-body {
  display: grid;
  grid-template-columns: 12rem minmax(0, 1fr);
  grid-template-areas: "rail head" "rail list";
  grid-template-rows: auto 1fr;
  gap: 0 2rem;
  margin-top: 1.5rem;
}
.results-top {
  grid-area: head;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  min-height: 2.75rem;
  margin-bottom: 0.75rem;
}
.filters {
  grid-area: rail;
}
.results {
  grid-area: list;
  min-width: 0;
}
.results-count {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0 0.75rem;
  min-width: 0;
}
.results-head {
  margin: 0;
  font-size: 1.125rem;
}
.copy-link {
  min-height: 2.75rem;
  font-size: 0.9375rem;
}
.results-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-left: auto;
}
.results-controls select {
  padding: 0.375rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  font: inherit;
}
.nothing {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  margin-bottom: 1rem;
}
.nothing p {
  margin: 0;
}
/* The filters' heading in "More options", on a phone: small, as the
   headings in the header's menus are. */
.more-filters-title {
  margin: 1rem 0 0;
  color: var(--muted);
  font-size: var(--text-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
@media (max-width: 40rem) {
  .search-body {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: "head" "list";
    grid-template-rows: auto;
    margin-top: 1rem;
  }
  .results-controls {
    margin-left: 0;
  }
  /* The select beside it says the order; the count has its line. */
  .order-note {
    display: none;
  }
  .more-panel {
    padding: 0.75rem 1rem 0.25rem;
  }
}
</style>
