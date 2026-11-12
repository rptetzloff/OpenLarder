<script setup lang="ts">
import { arrange } from "../shops";
import GrocerChooser from "../components/GrocerChooser.vue";
import DietCheck from "../components/DietCheck.vue";
import { grocerHref, grocerNow, loadGrocers } from "../grocery";
import { loadAllergens, notice as allergenNotice } from "../allergens";
import { buyHref, notes, shopName } from "../buying";
import TagEditor from "../components/TagEditor.vue";
import ReviewNotice from "../components/ReviewNotice.vue";
import HistoryPanel from "../components/HistoryPanel.vue";
import ReportButton from "../components/ReportButton.vue";
import { setRecipeTags } from "../tags";
import { computed, onMounted, ref } from "vue";
import { issueName } from "../books";
import FlagItem from "../components/FlagItem.vue";
import SwapForm from "../components/SwapForm.vue";
import SwapList from "../components/SwapList.vue";
import { type Flag, recipeFlags } from "../flags";
import type { Me } from "../me";
import { archivePage, markGone, type Recipe, removeRecipe } from "../recipes";
import { type OnShelf, onShelf } from "../shelf";
import RecipeActions from "../components/RecipeActions.vue";
import RecipeNotes from "../components/RecipeNotes.vue";
import type { Thing } from "../substitutions";

// Back from suggesting a change (RecipeFormPage's propose).
const proposed = new URLSearchParams(location.search).has("proposed");

// A recipe's page, laid out from Ray's wireframe (2026-11-08): where to find
// it, what goes in it, what uses it, and what can stand in.
const props = defineProps<{ id: string; user: Me | null | undefined }>();
const recipe = ref<Recipe | null>(null);
const missing = ref(false);
const failed = ref(false);
const error = ref("");
// Only whoever may deal with them gets any back: an admin, or who added it.
const flags = ref<Flag[]>([]);
const openFlags = computed(() => flags.value.filter((f) => !f.resolution));

onMounted(loadAllergens);
// The grocers, for the rows' Shop buttons.
onMounted(loadGrocers);
onMounted(async () => {
  try {
    const res = await fetch(`/api/recipes/${props.id}`);
    if (res.status === 404 || res.status === 422) missing.value = true;
    else if (!res.ok) failed.value = true;
    else {
      recipe.value = await res.json();
      editionId.value = recipe.value!.pages[0]?.edition_id ?? null;
      if (props.user && recipe.value!.source.kind === "book") showYours(recipe.value!);
      if (props.user !== null) flags.value = await recipeFlags(props.id);
      document.title = `${recipe.value!.title} · ${recipe.value!.source.title} · OpenLarder`;
    }
  } catch {
    failed.value = true;
  }
});

// A book's recipe: the edition whose page shows, the newest until chosen.
const editionId = ref<string | null>(null);
const edition = computed(
  () => recipe.value?.pages.find((p) => p.edition_id === editionId.value) ?? recipe.value?.pages[0],
);
const cover = computed(
  () => edition.value?.cover_url ?? recipe.value?.pages.find((p) => p.cover_url)?.cover_url ?? null,
);
function editionLabel(p: Recipe["pages"][number]) {
  const label =
    [p.published_year, p.isbn13 && `ISBN ${p.isbn13}`].filter(Boolean).join(" · ") || "Edition";
  return p.edition_id === yours.value ? `${label} (${whose.value})` : label;
}
// The edition on your shelf (routers/shelf.py), or failing that on a shelf
// shared with you, shown first if the recipe is in it.
const yours = ref<string | null>(null);
const whose = ref("yours");
// The book on your shelf, or one shared with you, for the sidebar to say.
const shelf = ref<OnShelf | null>(null);
const shelved = computed(() => {
  const s = shelf.value;
  if (!s) return null;
  const other = s.others.find((o) => o.on_shelf);
  if (!s.on_shelf && !other) return null;
  const editionId = s.on_shelf ? s.edition_id : other!.edition_id;
  const page = recipe.value?.pages.find((p) => p.edition_id === editionId);
  return {
    where: s.on_shelf ? "On your shelf" : `On ${other!.owner_name ?? "someone"}'s shelf`,
    edition: page
      ? [page.published_year, page.isbn13 && `ISBN ${page.isbn13}`].filter(Boolean).join(" · ")
      : "",
  };
});
async function showYours(r: Recipe) {
  try {
    const mine = await onShelf(r.source.id);
    shelf.value = mine;
    const has = (id: string | null) => !!id && r.pages.some((p) => p.edition_id === id);
    const other = mine.others.find((o) => has(o.edition_id));
    const found = has(mine.edition_id) ? mine.edition_id : (other?.edition_id ?? null);
    if (found) {
      if (found !== mine.edition_id) whose.value = `${other!.owner_name ?? "someone"}'s`;
      yours.value = found;
      editionId.value = found;
    }
  } catch {
    // The newest edition, as for anyone.
  }
}

// What the box says it's in, by the kind of source.
const findLabel = computed(() => {
  const r = recipe.value;
  if (!r) return "";
  if (r.web_page) return "Find it on";
  if (r.source.kind === "packaging") return "On the packaging of";
  if (r.source.kind === "family") return "From the family collection";
  return "Find it in";
});
// A line's ingredients a grocer can be searched for: one Shop button each.
type Line = Recipe["lines"][number];
const shoppable = (line: Line) => line.options.filter((o) => o.ingredient);
const between = (line: Line, j: number) =>
  j < line.options.length - 1 ? ", " : line.options.length > 2 ? ", or " : " or ";
// Commissions are said beside the links they're about (Ray, 2026-11-12):
// a line under the buy buttons, with the wording a shop's programme
// requires while its button is showing (Amazon's Associates statement),
// and one under the ingredients for all their Shop links.
const shopping = computed(
  () => !!grocerNow() && !!recipe.value?.lines.some((l) => shoppable(l).length),
);
// History, folded away until asked for from the sidebar's foot.
const showHistory = ref(false);
// The reader's first two shops as buttons; the rest behind "More shops".
const moreShops = ref(false);
const SHOPS_SHOWN = 2;
const shopsShown = computed(() =>
  moreShops.value ? buyLinks.value : buyLinks.value.slice(0, SHOPS_SHOWN),
);

// The ingredient lines, as typed, to paste into a shopping list.
const copyNote = ref("");
async function copyList() {
  try {
    await navigator.clipboard.writeText(recipe.value!.ingredients.join("\n"));
    copyNote.value = "Copied";
  } catch {
    copyNote.value = "Couldn't copy";
  }
  setTimeout(() => (copyNote.value = ""), 3000);
}

// What a swap entered here can replace: the ingredients, the recipes the
// lines cite, and the recipe itself.
const swapChoices = computed<Thing[]>(() => {
  const r = recipe.value;
  if (!r) return [];
  const seen = new Map<string, Thing>();
  for (const line of r.lines) {
    for (const o of line.options) {
      if (o.ingredient) seen.set(o.ingredient.id, { kind: "ingredient", ...o.ingredient });
      else if (o.recipe) seen.set(o.recipe.id, { kind: "recipe", id: o.recipe.id, name: o.recipe.title });
    }
  }
  seen.set(r.id, { kind: "recipe", id: r.id, name: r.title });
  return [...seen.values()];
});
// The book and page a printed swap starts at: this recipe's.
const firstPage = computed(() => recipe.value?.pages.find((p) => p.page) ?? recipe.value?.pages[0]);
const addingSwap = ref(false);

// "8 November 2026", for an archived copy's date.
function day(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { dateStyle: "long" }) : "";
}
// "Nov 8, 2026", for when it was added.
function shortDay(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" }) : "";
}

// The page's copy, and whether it's gone, for admins.
const pageNote = ref("");
async function archiveNow() {
  const page = recipe.value?.web_page;
  if (!page) return;
  try {
    await archivePage(page.id);
    pageNote.value = "Asked the Internet Archive for a copy. Reload in a minute or two to see it.";
  } catch (e) {
    pageNote.value = e instanceof Error ? e.message : String(e);
  }
}
async function setGone(gone: boolean) {
  const page = recipe.value?.web_page;
  if (!page) return;
  try {
    await markGone(page.id, gone);
    page.gone = gone;
  } catch (e) {
    pageNote.value = e instanceof Error ? e.message : String(e);
  }
}

async function remove() {
  if (!recipe.value || !confirm(`Remove “${recipe.value.title}” from the index?`)) return;
  try {
    await removeRecipe(recipe.value.id);
    location.href = `/sources/${recipe.value.source.id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

// Tags: the recipe's own; its source's come with it.
async function saveTags(ids: string[]) {
  recipe.value!.tags = await setRecipeTags(recipe.value!.id, ids);
}
// "book", "site": what the source is, for a tag that came from it.
const sourceWord = computed(() => (recipe.value?.source.kind === "book" ? "book" : "source"));

// This edition's shops, in the reader's order, without those hidden.
const buyLinks = computed(() => (edition.value ? arrange(edition.value.buy) : []));
</script>

<template>
  <article class="wide recipe-page">
    <p v-if="missing">There's no recipe here. It may have been removed, or the link is wrong.</p>
    <p v-else-if="failed" role="alert">This recipe couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!recipe" class="status">Loading…</p>
    <template v-else>
      <nav class="crumbs" aria-label="Breadcrumb">
        <a href="/sources">Sources</a>
        <span aria-hidden="true">/</span>
        <a :href="`/sources/${recipe.source.id}`">{{ recipe.source.title }}</a>
        <span aria-hidden="true">/</span>
        <span aria-current="page">{{ recipe.title }}</span>
      </nav>

      <div class="recipe-title">
        <h1>{{ recipe.title }}</h1>
        <ReviewNotice :review="recipe.review" :note="recipe.review_note" what="recipe" />
        <span v-if="recipe.used_in.length" class="badge">Component recipe</span>
      </div>
      <ul v-if="recipe.tags.length" class="tag-chips" aria-label="Tags">
        <li v-for="t in recipe.tags" :key="t.id">
          <a :href="`/search?tag=${t.id}`">{{ t.name }}</a
          ><span v-if="t.from_source" class="visually-hidden"> (from the {{ sourceWord }})</span>
        </li>
      </ul>
      <TagEditor
        v-if="recipe.editable"
        what="recipe"
        :selected="recipe.tags.filter((t) => !t.from_source).map((t) => t.id)"
        :inherited="recipe.tags.filter((t) => t.from_source).map((t) => t.id)"
        :can-add="!!user?.may_edit"
        :save="saveTags"
      />
      <RecipeActions v-if="user !== undefined" :recipe-id="recipe.id" :signed-in="!!user" />

      <div class="recipe-layout">
        <div class="recipe-main">
          <section class="find-it" aria-labelledby="find-it-label">
            <img v-if="cover" :src="cover" alt="" class="find-cover" />
            <div class="find-about">
              <p id="find-it-label" class="find-label">{{ findLabel }}</p>
              <p class="find-source">
                <a :href="`/sources/${recipe.source.id}`">{{ recipe.source.title }}</a>
              </p>
              <p v-if="recipe.source.credits.length" class="find-credits">
                <template v-for="(c, i) in recipe.source.credits" :key="c.author_id"
                  ><template v-if="i > 0">, </template
                  ><a :href="`/authors/${c.author_id}`">{{ c.credited_as }}</a></template
                >
              </p>

              <template v-if="recipe.web_page">
                <p class="find-place">
                  <a :href="recipe.web_page.url" rel="nofollow noopener" class="web-address">{{
                    recipe.web_page.url
                  }}</a>
                </p>
                <p v-if="recipe.web_page.gone">
                  This page no longer has the recipe.
                  <a
                    v-if="recipe.web_page.archive_url"
                    :href="recipe.web_page.archive_url"
                    rel="nofollow noopener"
                    >The Internet Archive's copy, from {{ day(recipe.web_page.archived_at) }}</a
                  >
                </p>
                <p v-else-if="recipe.web_page.archive_url">
                  <a :href="recipe.web_page.archive_url" rel="nofollow noopener"
                    >Archived copy, {{ day(recipe.web_page.archived_at) }}</a
                  >
                </p>
              </template>
              <template v-else-if="recipe.issue">
                <p class="find-place">{{ issueName(recipe.issue.label) }}</p>
                <p v-if="recipe.issue.page">Page {{ recipe.issue.page }}</p>
              </template>
              <template v-else-if="recipe.episode">
                <p class="find-place">
                  <a v-if="recipe.episode.url" :href="recipe.episode.url" rel="nofollow noopener">{{
                    recipe.episode.name
                  }}</a>
                  <template v-else>{{ recipe.episode.name }}</template>
                </p>
                <p v-if="recipe.episode.at || recipe.episode.aired_on">
                  {{ recipe.episode.at ? `At ${recipe.episode.at}` : ""
                  }}{{ recipe.episode.at && recipe.episode.aired_on ? " · " : ""
                  }}{{ recipe.episode.aired_on ? `Aired ${issueName(recipe.episode.aired_on)}` : "" }}
                </p>
              </template>
              <template v-else-if="edition">
                <div class="find-edition">
                  <p class="find-place">
                    {{ edition.page ? `Page ${edition.page}` : "Page not recorded yet" }}
                  </p>
                  <template v-if="recipe.pages.length > 1">
                    <label for="recipe-edition">Edition</label>
                    <select id="recipe-edition" v-model="editionId">
                      <option
                        v-for="p in recipe.pages"
                        :key="p.edition_id"
                        :value="p.edition_id"
                      >
                        {{ editionLabel(p) }}
                      </option>
                    </select>
                  </template>
                  <span v-else class="find-edition-only">{{ editionLabel(edition) }}</span>
                </div>
                <div v-if="buyLinks.length" class="buy-links">
                  <p class="buy-row">
                    <span class="muted">Buy the book</span>
                    <a
                      v-for="b in shopsShown"
                      :key="b.retailer"
                      :href="buyHref(b)"
                      rel="sponsored noopener"
                      class="buy-button"
                      >{{ shopName(b) }}</a
                    >
                    <button
                      v-if="buyLinks.length > SHOPS_SHOWN && !moreShops"
                      type="button"
                      class="link more-shops"
                      @click="moreShops = true"
                    >
                      More shops
                    </button>
                  </p>
                  <p class="buy-note">
                    OpenLarder may earn a commission if you buy through these links.
                    <template v-for="n in notes(shopsShown)" :key="n">{{ n }}{{ " " }}</template>
                    <a href="/terms#commissions">How this works</a>
                  </p>
                </div>
              </template>
              <p v-if="recipe.chapter" class="find-chapter">In “{{ recipe.chapter }}”</p>
            </div>
          </section>

          <section class="recipe-section">
            <div class="table-head">
              <h2>
                Ingredients
                <span class="ingredient-count">{{ recipe.lines.length }}</span>
              </h2>
              <span v-if="recipe.lines.length" class="copy-list">
                <span class="status" role="status">{{ copyNote }}</span>
                <button type="button" class="secondary" @click="copyList">Copy list</button>
              </span>
            </div>
            <ul v-if="recipe.lines.length" class="ingredient-lines ingredient-rows">
              <li v-for="(line, i) in recipe.lines" :key="i">
                <span class="row-names">
                  <template v-for="(o, j) in line.options" :key="j">
                    <span v-if="j > 0" class="muted">{{ between(line, j) }}</span>
                    <a v-if="o.recipe" :href="`/recipes/${o.recipe.id}`">{{ o.name }}</a>
                    <a v-else-if="o.ingredient" :href="`/ingredients/${o.ingredient.id}`">{{
                      o.name
                    }}</a>
                    <span v-else>{{ o.name }}</span>
                    <span v-if="o.page" class="page-ref">p. {{ o.page }}</span>
                  </template>
                </span>
                <!-- One Shop button for each ingredient the line names: "Shop",
                     or with a choice of them, the ingredient's name. -->
                <span v-if="grocerNow() && shoppable(line).length" class="row-shop">
                  <a
                    v-for="o in shoppable(line)"
                    :key="o.ingredient!.id"
                    :href="grocerHref(grocerNow()!, o.ingredient!.id)"
                    rel="sponsored noopener"
                    class="shop-pill"
                  >
                    <span>
                      <svg viewBox="0 0 20 20" aria-hidden="true">
                        <path d="M2 3h2.5l2 9.5h8.5l1.75-6.5H5.6" />
                        <circle cx="8" cy="16" r="1.1" />
                        <circle cx="14" cy="16" r="1.1" />
                      </svg>
                      <template v-if="shoppable(line).length > 1"
                        ><span class="visually-hidden">Shop for </span>{{ o.name }}</template
                      >
                      <template v-else
                        >Shop<span class="visually-hidden"> for {{ o.name.toLowerCase() }}</span></template
                      >
                    </span>
                  </a>
                </span>
              </li>
            </ul>
            <p v-else class="status">No ingredients recorded yet.</p>
            <div v-if="shopping" class="commission">
              <p class="muted">
                OpenLarder may earn a commission from these Shop links.
                <template v-if="grocerNow()?.note">{{ grocerNow()!.note }}{{ " " }}</template>
                <a href="/terms#commissions">How this works</a>
              </p>
              <GrocerChooser :signed-in="!!user" />
            </div>
          </section>

          <RecipeNotes v-if="user" :recipe-id="recipe.id" />

          <section
            v-if="recipe.allergens.length"
            class="recipe-section"
            aria-labelledby="recipe-allergens"
          >
            <h2 id="recipe-allergens">Allergens, meat and alcohol recorded</h2>
            <ul class="ingredient-lines recipe-allergens">
              <li v-for="a in recipe.allergens" :key="a.key">
                <strong
                  >{{ a.status === "contains" ? "Contains" : "May contain" }}
                  {{ a.label.toLowerCase() }}:</strong
                >{{ " " }}<template v-for="(x, i) in a.ingredients" :key="x.id"
                  ><template v-if="i > 0">, </template
                  ><a :href="`/ingredients/${x.id}`">{{ x.name }}</a
                  ><template v-if="a.status === 'contains' && x.status === 'may_contain'">
                    (may)</template
                  ></template
                >
              </li>
            </ul>
            <p class="allergen-notice">
              Only what the catalog records about these ingredients: one with nothing recorded may
              still contain any of them. {{ allergenNotice }}
            </p>
          </section>

          <section v-if="recipe.used_in.length" class="recipe-section">
            <h2>Used in</h2>
            <ul class="ingredient-lines">
              <li v-for="r in recipe.used_in" :key="r.id" class="used-in">
                <a :href="`/recipes/${r.id}`">{{ r.title }}</a>
                <span v-if="r.page" class="page-ref">p. {{ r.page }}</span>
              </li>
            </ul>
          </section>

          <section v-if="recipe.swaps.length || user?.may_edit" class="recipe-section">
            <div class="table-head">
              <h2>Swaps</h2>
              <button
                v-if="user?.may_edit && !addingSwap"
                type="button"
                class="link"
                @click="addingSwap = true"
              >
                + Add a swap
              </button>
            </div>
            <SwapList
              v-if="recipe.swaps.length"
              :swaps="recipe.swaps"
              :can-edit="!!user?.may_edit"
              @removed="(id) => (recipe!.swaps = recipe!.swaps.filter((s) => s.id !== id))"
            />
            <p v-else class="status">None recorded yet.</p>
            <SwapForm
              v-if="user?.may_edit && addingSwap"
              :choices="swapChoices"
              :book-id="recipe.source.id"
              :edition-id="firstPage?.edition_id"
              :page="firstPage?.page"
              @added="(s) => recipe!.swaps.push(s)"
            />
          </section>
        </div>

        <aside class="recipe-aside">
          <DietCheck
            v-if="recipe.lines.some((l) => l.options.some((o) => o.ingredient))"
            :recipe-id="recipe.id"
            :notice-shown="recipe.allergens.length > 0"
          />
          <p v-if="shelved" class="side-card shelf-status">
            <span class="tick" aria-hidden="true">
              <svg viewBox="0 0 20 20"><path d="M4.5 10.5l3.5 3.5 7.5-8.5" /></svg>
            </span>
            <span>
              <strong><a href="/shelf">{{ shelved.where }}</a></strong>
              <span v-if="shelved.edition" class="muted">{{ shelved.edition }}</span>
            </span>
          </p>
          <section v-if="openFlags.length" class="flag-box">
            <h2>Open flags</h2>
            <ul class="flag-list">
              <FlagItem
                v-for="f in openFlags"
                :key="f.id"
                :flag="f"
                :show-recipe="false"
                @resolved="(u) => (flags = flags.map((x) => (x.id === u.id ? u : x)))"
              />
            </ul>
          </section>
          <!-- A contributor suggests a change to a published recipe; a moderator applies it. -->
          <div
            v-if="
              !recipe.editable &&
              user?.may_claim &&
              recipe.review === 'published' &&
              recipe.source.kind !== 'family'
            "
            class="recipe-actions"
          >
            <p v-if="proposed" class="status" role="status">
              Thanks: your suggestion is with the moderators.
            </p>
            <a :href="`/recipes/${recipe.id}/propose`" class="button-outline">Suggest a change</a>
          </div>
          <div v-if="recipe.editable" class="recipe-actions">
            <a :href="`/recipes/${recipe.id}/edit`" class="button-outline">Edit</a>
            <button type="button" class="secondary" @click="remove">Remove</button>
            <template v-if="recipe.web_page && user?.may_edit">
              <button
                v-if="!recipe.web_page.archive_url"
                type="button"
                class="link"
                @click="archiveNow"
              >
                Archive now
              </button>
              <button type="button" class="link" @click="setGone(!recipe.web_page.gone)">
                {{ recipe.web_page.gone ? "The page is back" : "The page is gone" }}
              </button>
            </template>
          </div>
          <p v-if="pageNote" class="status" role="status">{{ pageNote }}</p>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <div class="aside-foot muted">
            <span v-if="recipe.added_by || recipe.added_on"
              >Added{{ recipe.added_by ? ` by ${recipe.added_by}` : ""
              }}{{ recipe.added_on ? `, ${shortDay(recipe.added_on)}` : "" }}</span
            >
            <button
              type="button"
              class="link"
              :aria-expanded="showHistory"
              aria-controls="recipe-history"
              @click="showHistory = !showHistory"
            >
              History
            </button>
            <ReportButton kind="recipe" :id="id" />
          </div>
        </aside>
      </div>
      <div id="recipe-history">
        <HistoryPanel
          v-if="showHistory"
          kind="recipes"
          :id="id"
          :can-revert="!!user?.may_edit"
          start-open
        />
      </div>
    </template>
  </article>
</template>

<style scoped>
/* Ray's cleanup pass, section 2 (2026-11-11). */
.buy-button {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  padding: 0 0.875rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  color: var(--fg);
  font-size: var(--text-sm);
  font-weight: 600;
  text-decoration: none;
}
.buy-button:hover {
  border-color: var(--fg);
}
.more-shops {
  min-height: 2.75rem;
  font-size: var(--text-sm);
}
.buy-note {
  font-size: var(--text-sm);
}
.ingredient-count {
  margin-left: 0.25rem;
  color: var(--muted);
  font-weight: 400;
}
/* A row: the names on the left, Shop at the right end. */
.ingredient-rows {
  background: var(--surface);
}
.ingredient-rows li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.25rem 0.75rem;
  padding: 0 0.875rem;
  min-height: 2.75rem;
}
.row-names {
  padding: 0.5rem 0;
  font-weight: 500;
}
.row-names a {
  color: var(--fg);
  text-decoration: none;
}
.row-names a:hover,
.row-names a:focus-visible {
  text-decoration: underline;
}
.row-names .muted {
  font-weight: 400;
}
.row-shop {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0 0.25rem;
}
/* 44px to tap, drawn as a smaller pill. */
.shop-pill {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  color: var(--muted);
  font-size: var(--text-sm);
  text-decoration: none;
  white-space: nowrap;
}
.shop-pill > span {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.625rem;
  border: 1px solid var(--line);
  border-radius: 999px;
}
.shop-pill:hover > span,
.shop-pill:focus-visible > span {
  border-color: var(--border);
  color: var(--fg);
}
.shop-pill svg {
  width: 1rem;
  height: 1rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.4;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.commission {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  margin-top: 0.5rem;
  font-size: var(--text-sm);
}
.commission p {
  margin: 0;
}
/* The sidebar's cards and its foot. */
.side-card {
  margin: 0;
  padding: 0.875rem 1rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  background: var(--surface);
}
.shelf-status {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.shelf-status > span:last-child {
  display: grid;
}
.shelf-status a {
  color: var(--fg);
}
.shelf-status .muted {
  font-size: var(--text-sm);
}
.tick {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: var(--accent);
  color: var(--on-accent);
}
.tick svg {
  width: 0.9rem;
  height: 0.9rem;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.25;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.aside-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0 0.75rem;
  font-size: var(--text-sm);
}
.aside-foot :deep(.report-problem) {
  margin-top: 0;
}
.aside-foot :deep(.report-form) {
  flex-basis: 100%;
}
.aside-foot :deep(button.link) {
  min-height: 2.75rem;
}
</style>
