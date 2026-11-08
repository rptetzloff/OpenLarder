<script setup lang="ts">
import { onMounted, ref } from "vue";
import { type BookSummary, KIND_NAMES, listSources } from "../books";
import IngredientPicker from "../components/IngredientPicker.vue";
import type { Named } from "../ingredients";

// Search starts here: words of a title go to the Search page as q, chosen
// ingredients as i, as its own links do.
const q = ref("");
const have = ref<Named[]>([]);
const MAX_INGREDIENTS = 10;
function searchTitles() {
  const words = q.value.trim();
  if (words) location.href = `/search?${new URLSearchParams({ q: words })}`;
}
function findRecipes() {
  const query = new URLSearchParams();
  for (const i of have.value) query.append("i", i.id);
  location.href = `/search?${query}`;
}

const recent = ref<BookSummary[] | null>(null);
onMounted(async () => {
  document.title = "OpenLarder";
  recent.value = (await listSources("", 0, 5, "recent").catch(() => null))?.sources ?? [];
});

// Under a card's title: who made it, or the site, then how many recipes.
function byline(s: BookSummary) {
  const who = s.authors.join(", ") || s.host;
  const count = `${s.recipes} ${s.recipes === 1 ? "recipe" : "recipes"}`;
  return who ? `${who} · ${count}` : count;
}
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
          <p class="help">Up to 10 ingredients. Recipes using more of them rank higher.</p>
        </div>
      </div>
    </section>

    <section class="home-section">
      <div class="section-head">
        <h2>Recently added sources</h2>
        <a href="/sources">Browse all sources</a>
      </div>
      <p v-if="recent && !recent.length" class="status">Nothing yet.</p>
      <ul v-else-if="recent" class="cover-grid">
        <li v-for="s in recent" :key="s.id">
          <a :href="`/sources/${s.id}`" class="cover-card">
            <img v-if="s.cover_url" :src="s.cover_url" alt="" loading="lazy" />
            <span v-else class="cover-blank" aria-hidden="true"></span>
            <span class="kind">{{ KIND_NAMES[s.kind] }}</span>
            <strong>{{ s.title }}</strong>
            <span class="byline">{{ byline(s) }}</span>
          </a>
        </li>
      </ul>
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
