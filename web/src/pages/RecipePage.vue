<script setup lang="ts">
import { arrange } from "../shops";
import { buyHref, DISCLOSURE, notes } from "../buying";
import TagEditor from "../components/TagEditor.vue";
import { setRecipeTags } from "../tags";
import { computed, onMounted, ref } from "vue";
import { issueName } from "../books";
import FlagItem from "../components/FlagItem.vue";
import SwapForm from "../components/SwapForm.vue";
import SwapList from "../components/SwapList.vue";
import { type Flag, recipeFlags } from "../flags";
import type { Me } from "../me";
import { archivePage, markGone, type Recipe, removeRecipe } from "../recipes";
import type { Thing } from "../substitutions";

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

onMounted(async () => {
  try {
    const res = await fetch(`/api/recipes/${props.id}`);
    if (res.status === 404 || res.status === 422) missing.value = true;
    else if (!res.ok) failed.value = true;
    else {
      recipe.value = await res.json();
      editionId.value = recipe.value!.pages[0]?.edition_id ?? null;
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
  return [p.published_year, p.isbn13 && `ISBN ${p.isbn13}`].filter(Boolean).join(" · ") || "Edition";
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
// Where the amounts and method are, said plainly.
const methodWhere = computed(() => {
  const r = recipe.value;
  if (!r) return "";
  if (r.web_address) return r.source.kind === "social" ? "on the post" : "on the page";
  if (r.issue) return "in the issue";
  if (r.episode) return "in the episode";
  if (r.source.kind === "packaging") return "on the packaging";
  if (r.source.kind === "family") return "with the family's copy";
  return "in the book";
});

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

// "8 November 2026", for an archived copy's date and when it was added.
function day(iso: string | null) {
  return iso ? new Date(iso).toLocaleDateString(undefined, { dateStyle: "long" }) : "";
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
        :can-add="!!user?.is_admin"
        :save="saveTags"
      />

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
                    <span>Buy the book:</span>
                    <a
                      v-for="b in buyLinks"
                      :key="b.retailer"
                      :href="buyHref(b)"
                      rel="sponsored noopener"
                      >{{ b.label }}</a
                    >
                  </p>
                  <p class="buy-note">{{ DISCLOSURE }}</p>
                  <p v-for="n in notes(buyLinks)" :key="n" class="buy-note">{{ n }}</p>
                </div>
              </template>
              <p v-if="recipe.chapter" class="find-chapter">In “{{ recipe.chapter }}”</p>
            </div>
          </section>

          <p class="reference-note">
            OpenLarder is a cookbook reference: it tells you where this recipe is and what goes in
            it. The amounts and the method are {{ methodWhere }}.
          </p>

          <section class="recipe-section">
            <div class="table-head">
              <h2>Ingredients ({{ recipe.lines.length }})</h2>
              <span v-if="recipe.lines.length" class="copy-list">
                <span class="status" role="status">{{ copyNote }}</span>
                <button type="button" class="secondary" @click="copyList">Copy list</button>
              </span>
            </div>
            <ul v-if="recipe.lines.length" class="ingredient-lines">
              <li v-for="(line, i) in recipe.lines" :key="i">
                <template v-for="(o, j) in line.options" :key="j">
                  <template v-if="j > 0">{{
                    j < line.options.length - 1 ? ", " : line.options.length > 2 ? ", or " : " or "
                  }}</template>
                  <a v-if="o.recipe" :href="`/recipes/${o.recipe.id}`">{{ o.name }}</a>
                  <a v-else-if="o.ingredient" :href="`/ingredients/${o.ingredient.id}`">{{
                    o.name
                  }}</a>
                  <template v-else>{{ o.name }}</template>
                  <span v-if="o.page" class="page-ref">p. {{ o.page }}</span>
                </template>
              </li>
            </ul>
            <p v-else class="status">No ingredients recorded yet.</p>
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

          <section v-if="recipe.swaps.length || user?.is_admin" class="recipe-section">
            <div class="table-head">
              <h2>Swaps</h2>
              <button
                v-if="user?.is_admin && !addingSwap"
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
              :can-edit="!!user?.is_admin"
              @removed="(id) => (recipe!.swaps = recipe!.swaps.filter((s) => s.id !== id))"
            />
            <p v-else class="status">None recorded yet.</p>
            <SwapForm
              v-if="user?.is_admin && addingSwap"
              :choices="swapChoices"
              :book-id="recipe.source.id"
              :edition-id="firstPage?.edition_id"
              :page="firstPage?.page"
              @added="(s) => recipe!.swaps.push(s)"
            />
          </section>
        </div>

        <aside class="recipe-aside">
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
          <div v-if="recipe.editable" class="recipe-actions">
            <a :href="`/recipes/${recipe.id}/edit`" class="button-outline">Edit</a>
            <button type="button" class="secondary" @click="remove">Remove</button>
            <template v-if="recipe.web_page && user?.is_admin">
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
          <p v-if="recipe.added_by || recipe.added_on" class="status added-by">
            Added{{ recipe.added_by ? ` by ${recipe.added_by}` : ""
            }}{{ recipe.added_on ? ` on ${day(recipe.added_on)}` : "" }}
          </p>
        </aside>
      </div>
    </template>
  </article>
</template>
