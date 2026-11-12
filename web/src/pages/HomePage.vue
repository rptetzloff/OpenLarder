<script setup lang="ts">
import SourceRow from "../components/SourceRow.vue";
import { onMounted, ref } from "vue";
import { type BookSummary, listSources } from "../books";
import IngredientPicker from "../components/IngredientPicker.vue";
import { ingredientsNamed, type Named } from "../ingredients";

// Search starts here: words of a title go to the Search page as q, chosen
// ingredients as i, as its own links do.
const q = ref("");
const have = ref<Named[]>([]);
// As many as Search takes.
const MAX_INGREDIENTS = 30;
function searchTitles() {
  const words = q.value.trim();
  if (words) location.href = `/search?${new URLSearchParams({ q: words })}`;
}
function findRecipes() {
  const query = new URLSearchParams();
  for (const i of have.value) query.append("i", i.id);
  location.href = `/search?${query}`;
}

// Finished searches to try, under "Cook with what you have" (Ray's cleanup
// pass, section 11): well-used ingredients, so each finds plenty. Checked
// against the catalog on 2026-11-12: at least twenty recipes use all three
// of each. One shows only when every ingredient of it is in the catalog.
const EXAMPLES = [
  ["chicken", "lemon", "garlic"],
  ["egg", "butter", "flour"],
  ["onion", "olive oil", "tomato"],
  ["carrot", "onion", "celery"],
];
const examples = ref<{ label: string; href: string }[]>([]);
async function findExamples() {
  const found = await ingredientsNamed([...new Set(EXAMPLES.flat())]).catch(() => []);
  const ids = new Map(found.map((i) => [i.name.toLowerCase(), i.id]));
  examples.value = EXAMPLES.filter((names) => names.every((n) => ids.has(n))).map((names) => ({
    label: names.join(" + "),
    href: `/search?${new URLSearchParams(names.map((n) => ["i", ids.get(n)!]))}`,
  }));
}

// The row of sources: a row's worth to scroll through, and none that
// opens on an empty page (Ray's cleanup pass, sections 4 and 9). The newest
// with a recipe; when fewer than six have one, those by how many instead.
const ROW = 20;
const ENOUGH = 6;
const recent = ref<BookSummary[] | null>(null);
const rowTitle = ref("Recently added sources");
onMounted(async () => {
  document.title = "OpenLarder";
  findExamples();
  const newest = await listSources("", 0, ROW, "recent", [], 1).catch(() => null);
  if (newest && newest.total < ENOUGH) {
    const most = await listSources("", 0, ROW, "recipes", [], 1).catch(() => null);
    if (most) {
      rowTitle.value = "Most indexed sources";
      recent.value = most.sources;
      return;
    }
  }
  recent.value = newest?.sources ?? [];
});
</script>

<template>
  <div class="home">
    <section class="hero">
      <div class="hero-inner">
        <h1>Find the recipe on your shelf.</h1>
        <p class="lede">
          A free, open reference to where recipes live: which cookbook, magazine or website, which
          page, and what goes in it.
        </p>
        <form class="hero-search" role="search" @submit.prevent="searchTitles">
          <label for="home-q" class="visually-hidden">Search recipe titles</label>
          <input
            id="home-q"
            v-model="q"
            type="search"
            autocomplete="off"
            placeholder="Search recipe titles"
          />
          <button type="submit" class="primary">Search</button>
        </form>
        <div class="hero-have">
          <IngredientPicker
            input-id="home-have"
            label="Cook with what you have"
            placeholder="Add an ingredient"
            :exclude="have.map((i) => i.id)"
            :disabled="have.length >= MAX_INGREDIENTS"
            @pick="(i) => have.length < MAX_INGREDIENTS && have.push(i)"
          />
          <ul v-if="have.length" class="chosen">
            <li v-for="(i, n) in have" :key="i.id">
              {{ i.name }}
              <button
                type="button"
                class="link"
                :aria-label="`Remove ${i.name}`"
                @click="have.splice(n, 1)"
              >
                ×
              </button>
            </li>
          </ul>
          <button v-if="have.length" type="button" class="primary" @click="findRecipes">
            Find recipes
          </button>
          <p class="help">Up to 30 ingredients. Recipes using more of them rank higher.</p>
          <p v-if="examples.length" class="try">
            <span class="muted">Try:</span>
            <!-- Named by what it does and the words on it: a name that
                 left the visible words out would fail speech control. -->
            <a v-for="e in examples" :key="e.href" :href="e.href"
              ><span class="visually-hidden">Search for recipes using </span
              ><span class="chip">{{ e.label }}</span></a
            >
          </p>
        </div>
      </div>
    </section>

    <section class="home-section" aria-labelledby="recent-title">
      <div class="section-head">
        <h2 id="recent-title">{{ rowTitle }}</h2>
        <a href="/sources">Browse all sources</a>
      </div>
      <p v-if="recent && !recent.length" class="status">Nothing yet.</p>
      <SourceRow v-else-if="recent" :sources="recent" labelledby="recent-title" />
    </section>

    <section class="home-section value-cards">
      <div>
        <h3>A reference, not a recipe site</h3>
        <p>
          Which source, which page, and the ingredients by name. Amounts and method stay in the
          book.
        </p>
      </div>
      <div>
        <h3>Search by what you have</h3>
        <p>
          Ingredients are matched however a source names them, and a broader one finds what's
          under it: cheese finds cheddar.
        </p>
      </div>
      <div>
        <h3>Free and open</h3>
        <p>
          Free to use, and the catalog is open data under the ODbL, with a
          <a href="/api/docs">public API</a>.
        </p>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* The example searches: chips like a tag's, each 44px to tap. */
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
</style>
