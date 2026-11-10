<script setup lang="ts">
import LarderPicker from "../components/LarderPicker.vue";
import { KINDS, listTags, type Tag } from "../tags";
import { computed, onMounted, ref, watch } from "vue";
import { findBooks } from "../books";
import {
  listIngredients,
  type Named,
  type SearchResult,
  searchRecipes,
  whereItIs,
} from "../ingredients";

import type { Me } from "../me";

defineProps<{ user?: Me | null }>();
document.title = "Search · OpenLarder";

// What can I make from these sources with what I have? Ingredients you have
// rank the recipes (the more of a recipe you have, the higher); title words,
// sources and kinds of source narrow them. All of it is kept in the address
// (?i=…&q=…&source=…&kind=…&page=…), so a search can be bookmarked or shared.
// Laid out from Ray's wireframe, 2026-11-08.
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
// What you don't have or want (Ray, 2026-11-08): recipes needing one are left
// out; a line offering something else ("butter or oil") doesn't need it.
const unwanted = ref<Named[]>([]);
const shelf = ref<Named[]>([]);
const title = ref(params.get("q") ?? "");
// Every kind until some are unticked; the address lists them only then.
const asked = params.getAll("kind").filter((k) => ALL_KINDS.includes(k));
const kinds = ref<string[]>(asked.length ? asked : [...ALL_KINDS]);
const moreKinds = ref(KIND_GROUPS.slice(3).some((g) => g.kinds.some((k) => !kinds.value.includes(k))));
const page = ref(Math.max(1, Number(params.get("page")) || 1));
// Recipes with every tag ticked; diet and course show, the rest on request.
const allTags = ref<Tag[]>([]);
const tags = ref<string[]>(params.getAll("tag"));
const moreTags = ref(false);
const tagGroups = computed(() =>
  KINDS.map((k) => ({ ...k, tags: allTags.value.filter((t) => t.kind === k.kind) })).filter(
    (k) => k.tags.length && (moreTags.value || k.kind === "diet" || k.kind === "course"),
  ),
);
const result = ref<SearchResult | null>(null);
const missing = ref(0);
const failed = ref(false);
const loading = ref(false);
let latest = 0;

const narrowedKinds = computed(() =>
  kinds.value.length === ALL_KINDS.length ? [] : kinds.value,
);
const searching = computed(
  () => useLarder.value || !!chosen.value.length || !!title.value.trim() || !!tags.value.length,
);

function toAddress() {
  const url = new URL(location.href);
  for (const key of ["i", "x", "book", "source", "q", "kind", "tag", "page", "larder", "ll", "li", "lx"]) {
    url.searchParams.delete(key);
  }
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
      },
    );
    if (mine !== latest) return;
    result.value = found;
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
function dropUnwanted(id: string) {
  unwanted.value = unwanted.value.filter((i) => i.id !== id);
  document.getElementById("search-unwanted")?.focus();
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
function dropSource(id: string) {
  shelf.value = shelf.value.filter((b) => b.id !== id);
  document.getElementById("search-source")?.focus();
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
  document.getElementById("results")?.scrollIntoView();
}

// "Onion", "Onion and Frog's Legs", "Onion, Garlic and Frog's Legs".
function inWords(names: string[]) {
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : (names[0] ?? "");
}

const summary = computed(() => {
  const r = result.value;
  if (!r) return "";
  return `${r.total.toLocaleString()} ${r.total === 1 ? "recipe" : "recipes"}`;
});

onMounted(async () => {
  listTags()
    .then((found) => {
      allTags.value = found;
      // A tag in the link that's in the hidden kinds: show them.
      if (found.some((t) => tags.value.includes(t.id) && !["diet", "course"].includes(t.kind))) {
        moreTags.value = true;
      }
    })
    .catch(() => {});
  const ids = params.getAll("i").slice(0, MAX_INGREDIENTS);
  const sources = [...params.getAll("source"), ...params.getAll("book")].slice(0, MAX_SOURCES);
  try {
    if (!ids.length && !title.value.trim() && !tags.value.length && !useLarder.value) {
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
    if (missing.value || page.value > 1) run(page.value);
  } catch {
    failed.value = true;
  }
});
</script>

<template>
  <article class="wide search-page">
    <h1>Search</h1>

    <form class="search-panel" role="search" @submit.prevent="run()">
      <LarderPicker
        v-if="user"
        v-model:lists="larderLists"
        v-model:only="larderOnly"
        v-model:leave-out="larderOut"
        :counted="result?.larder_items"
        :tick-all="larderAll"
        @change="run()"
      />
      <label for="search-ingredient">I have</label>
      <div class="chip-input" @click="($event.currentTarget as HTMLElement).querySelector('input')?.focus()">
        <span v-for="i in chosen" :key="i.id" class="chip">
          {{ i.name }}
          <button type="button" :aria-label="`Remove ${i.name}`" @click.stop="dropIngredient(i.id)">
            ×
          </button>
        </span>
        <input
          id="search-ingredient"
          v-model="ingredientFind.query.value"
          type="search"
          autocomplete="off"
          :placeholder="`Add an ingredient (up to ${MAX_INGREDIENTS})`"
          aria-describedby="search-ingredient-help"
          :disabled="chosen.length >= MAX_INGREDIENTS"
          @keydown.enter.prevent="
            ingredientFind.suggestions.value[0] && addIngredient(ingredientFind.suggestions.value[0])
          "
        />
      </div>
      <ul v-if="ingredientFind.suggestions.value.length" class="suggestions">
        <li v-for="s in ingredientFind.suggestions.value" :key="s.id">
          <button type="button" class="link" @click="addIngredient(s)">{{ s.name }}</button>
          <span class="page-ref">
            {{ s.recipes.toLocaleString() }} {{ s.recipes === 1 ? "recipe" : "recipes" }}
          </span>
        </li>
      </ul>
      <p id="search-ingredient-help" class="help">
        An ingredient also finds what's under it: cheese finds cheddar.
      </p>

      <label for="search-unwanted" class="panel-gap">I don't have or don't want</label>
      <div class="chip-input" @click="($event.currentTarget as HTMLElement).querySelector('input')?.focus()">
        <span v-for="i in unwanted" :key="i.id" class="chip chip-unwanted">
          {{ i.name }}
          <button type="button" :aria-label="`Remove ${i.name}`" @click.stop="dropUnwanted(i.id)">
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
          @keydown.enter.prevent="
            unwantedFind.suggestions.value[0] && addUnwanted(unwantedFind.suggestions.value[0])
          "
        />
      </div>
      <ul v-if="unwantedFind.suggestions.value.length" class="suggestions">
        <li v-for="s in unwantedFind.suggestions.value" :key="s.id">
          <button type="button" class="link" @click="addUnwanted(s)">{{ s.name }}</button>
          <span class="page-ref">
            {{ s.recipes.toLocaleString() }} {{ s.recipes === 1 ? "recipe" : "recipes" }}
          </span>
        </li>
      </ul>
      <p id="search-unwanted-help" class="help">
        Recipes that need one are left out. One that offers another choice, like “butter or oil”,
        stays.
      </p>

      <div class="panel-row">
        <div>
          <label for="search-title">Title words</label>
          <input
            id="search-title"
            v-model="title"
            type="search"
            autocomplete="off"
            maxlength="200"
            placeholder="e.g. biscuit"
          />
        </div>
        <div>
          <label for="search-source">In sources <span class="optional">(optional)</span></label>
          <div class="chip-input" @click="($event.currentTarget as HTMLElement).querySelector('input')?.focus()">
            <span v-for="b in shelf" :key="b.id" class="chip">
              {{ b.name }}
              <button type="button" :aria-label="`Remove ${b.name}`" @click.stop="dropSource(b.id)">
                ×
              </button>
            </span>
            <input
              id="search-source"
              v-model="sourceFind.query.value"
              type="search"
              autocomplete="off"
              placeholder="Type a title, author or site"
              :disabled="shelf.length >= MAX_SOURCES"
              @keydown.enter.prevent="
                sourceFind.suggestions.value[0] && addSource(sourceFind.suggestions.value[0])
              "
            />
          </div>
          <ul v-if="sourceFind.suggestions.value.length" class="suggestions">
            <li v-for="b in sourceFind.suggestions.value" :key="b.id">
              <button type="button" class="link" @click="addSource(b)">{{ b.title }}</button>
              <span v-if="b.authors.length" class="page-ref">{{ b.authors.join(", ") }}</span>
            </li>
          </ul>
        </div>
      </div>

      <div class="panel-actions">
        <button type="submit" class="primary">Search</button>
        <button type="button" class="secondary" @click="copyLink">
          Copy link to this search
        </button>
        <span class="status" role="status">{{ copyNote }}</span>
      </div>
    </form>

    <p v-if="missing" class="status">
      {{ missing === 1 ? "Something" : `${missing} things` }} in this link no longer
      {{ missing === 1 ? "exists" : "exist" }}, perhaps merged into another, so the search is
      without {{ missing === 1 ? "it" : "them" }}.
    </p>

    <div class="search-body">
      <aside class="filters" aria-label="Filters">
        <fieldset>
          <legend>Source kind</legend>
          <template v-for="(g, n) in KIND_GROUPS" :key="g.label">
            <label v-if="n < 3 || moreKinds" class="check">
              <input
                type="checkbox"
                :checked="groupTicked(g.kinds)"
                @change="toggleGroup(g.kinds, ($event.target as HTMLInputElement).checked)"
              />
              {{ g.label }}
            </label>
          </template>
          <button
            type="button"
            class="link"
            :aria-expanded="moreKinds"
            @click="moreKinds = !moreKinds"
          >
            {{ moreKinds ? "Fewer kinds" : "More kinds" }}
          </button>
        </fieldset>
        <fieldset v-for="g in tagGroups" :key="g.kind">
          <legend>{{ g.label }}</legend>
          <label v-for="t in g.tags" :key="t.id" class="check">
            <input
              type="checkbox"
              :checked="tags.includes(t.id)"
              @change="toggleTag(t.id, ($event.target as HTMLInputElement).checked)"
            />
            {{ t.name }}
          </label>
        </fieldset>
        <button
          v-if="allTags.length"
          type="button"
          class="link"
          :aria-expanded="moreTags"
          @click="moreTags = !moreTags"
        >
          {{ moreTags ? "Fewer tags" : "Cuisine and technique" }}
        </button>
      </aside>

      <section id="results" class="results" aria-live="polite" :aria-busy="loading">
        <p v-if="failed" role="alert">The search didn't work. Try again.</p>
        <p v-else-if="!searching" class="status">
          Add what you have, words of a title or a tag, and the recipes you're closest to making
          come first, with where to find them.
        </p>
        <template v-else-if="result">
          <h2 class="results-head">
            {{ summary }}
            <span v-if="chosen.length || useLarder" class="muted"> · closest to made first</span>
          </h2>
          <ul class="hits">
            <li v-for="r in result.recipes" :key="r.id" class="hit">
              <img v-if="r.cover_url" :src="r.cover_url" alt="" class="hit-cover" loading="lazy" />
              <span v-else class="hit-cover" aria-hidden="true"></span>
              <div>
                <h3><a :href="`/recipes/${r.id}`">{{ r.title }}</a></h3>
                <p class="hit-where">
                  <a :href="`/sources/${r.source_id}`">{{ r.source_title }}</a
                  ><template v-if="whereItIs(r)"> · {{ whereItIs(r) }}</template>
                </p>
                <template v-if="r.lines !== null">
                  <p class="hit-have">Uses your {{ inWords(r.uses) }}</p>
                  <p class="hit-needs">
                    {{ r.needs.length ? `Still needs: ${r.needs.join(", ")}` : "Nothing else on its list" }}
                  </p>
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
