<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { type Book, SHOWS } from "../books";
import { checkLines, type LineReview, type Recipe, saveRecipe } from "../recipes";

// New when bookId is given, editing when recipeId is.
const props = defineProps<{ bookId?: string; recipeId?: string }>();

const book = ref<Book | null>(null);
const title = ref("");
const ingredients = ref("");
// A website's recipe: the page it's on.
const webAddress = ref("");
// A social media account's recipes are on its posts, by address, too.
const onWeb = computed(() => ["website", "social"].includes(book.value?.kind ?? ""));
// Packaging's and a family collection's recipes are just in them.
const onPackaging = computed(() => book.value?.kind === "packaging");
const inFamily = computed(() => book.value?.kind === "family");
// A magazine's or newspaper's recipe: its issue (name or date) and page.
const inIssue = computed(() => ["magazine", "newspaper"].includes(book.value?.kind ?? ""));
const issue = ref("");
const issueDate = ref("");
const issuePage = ref("");
// A TV show's, podcast's or video channel's: which episode, and the time in
// it. Numbers are kept as typed, "" for none.
const inEpisode = computed(() => SHOWS.includes(book.value?.kind ?? ""));
const season = ref<number | "">("");
const episodeNumber = ref<number | "">("");
const episodeTitle = ref("");
const episodeAddress = ref("");
const airedOn = ref("");
const at = ref("");
// What the recipe is in, for the form's wording.
const place = computed(() =>
  onWeb.value
    ? book.value?.kind === "social"
      ? "post"
      : "page"
    : inIssue.value
      ? "issue"
      : inEpisode.value
        ? "episode"
        : onPackaging.value
          ? "packaging"
          : inFamily.value
            ? "family's copy"
            : "book",
);
// Per edition: is the recipe in it, and on which page.
const editions = ref<{ id: string; label: string; included: boolean; page: string }[]>([]);
const error = ref("");
const saving = ref(false);
const loadFailed = ref(false);

const example = ["rhubarb", "caster sugar", "vanilla pod"].join("\n");
const heading = computed(() => (props.recipeId ? "Edit recipe" : "Add a recipe"));

function label(e: { title: string | null; published_year: number | null; isbn13: string | null }) {
  return [e.title ?? book.value?.title, e.published_year, e.isbn13 && `ISBN ${e.isbn13}`]
    .filter(Boolean)
    .join(" · ");
}

onMounted(async () => {
  try {
    let existing: Recipe | null = null;
    let bookId = props.bookId;
    if (props.recipeId) {
      const res = await fetch(`/api/recipes/${props.recipeId}`);
      if (!res.ok) throw new Error();
      existing = await res.json();
      bookId = existing!.source.id;
    }
    const res = await fetch(`/api/sources/${bookId}`);
    if (!res.ok) throw new Error();
    book.value = await res.json();
    const pages = new Map(existing?.pages.map((p) => [p.edition_id, p.page]) ?? []);
    editions.value = book.value!.editions.map((e) => ({
      id: e.id,
      label: label(e),
      // A new recipe is assumed to be in every edition until unticked.
      included: existing ? pages.has(e.id) : true,
      page: pages.get(e.id) ?? "",
    }));
    if (existing) {
      title.value = existing.title;
      webAddress.value = existing.web_address ?? "";
      issue.value = existing.issue?.label ?? "";
      issueDate.value = existing.issue?.published_on ?? "";
      issuePage.value = existing.issue?.page ?? "";
      season.value = existing.episode?.season ?? "";
      episodeNumber.value = existing.episode?.number ?? "";
      episodeTitle.value = existing.episode?.title ?? "";
      episodeAddress.value = existing.episode?.url ?? "";
      airedOn.value = existing.episode?.aired_on ?? "";
      at.value = existing.episode?.at ?? "";
      ingredients.value = existing.ingredients.join("\n");
    }
    document.title = `${heading.value} · ${book.value!.title} · OpenLarder`;
  } catch {
    loadFailed.value = true;
  }
});

// The entry rules, checked as the lines are typed (issue #26). Advice only:
// a line can be an exception, so saving never waits on it.
const reviews = ref<{ index: number; line: string; review: LineReview }[]>([]);
let asked = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
watch(ingredients, () => {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const mine = ++asked;
    const lines = ingredients.value.split("\n");
    try {
      const found = await checkLines(lines);
      if (mine !== asked) return;
      reviews.value = found
        .map((review, index) => ({ index, line: lines[index].trim(), review }))
        .filter((r) => r.review.problems.length);
    } catch {
      if (mine === asked) reviews.value = [];
    }
  }, 400);
});

// Replaces (or with null removes) a line, if it still reads as it did.
function fix(index: number, line: string, replacement: string | null) {
  const lines = ingredients.value.split("\n");
  if (lines[index]?.trim() !== line) return;
  if (replacement === null) lines.splice(index, 1);
  else lines[index] = replacement;
  ingredients.value = lines.join("\n");
}

async function save() {
  saving.value = true;
  error.value = "";
  try {
    const id = await saveRecipe(
      {
        title: title.value,
        editions:
          onWeb.value || inIssue.value || inEpisode.value || onPackaging.value || inFamily.value
          ? []
          : editions.value
              .filter((e) => e.included)
              .map((e) => ({ edition_id: e.id, page: e.page.trim() || null })),
        web_address: onWeb.value ? webAddress.value : null,
        issue: inIssue.value ? issue.value : null,
        issue_date: inIssue.value && issueDate.value ? issueDate.value : null,
        issue_page: inIssue.value ? issuePage.value : null,
        episode: inEpisode.value
          ? {
              season: season.value === "" ? null : season.value,
              number: episodeNumber.value === "" ? null : episodeNumber.value,
              title: episodeTitle.value || null,
              address: episodeAddress.value || null,
              aired_on: airedOn.value || null,
              at: at.value || null,
            }
          : null,
        ingredients: ingredients.value.split("\n"),
      },
      props.recipeId ? { recipeId: props.recipeId } : { bookId: book.value!.id },
    );
    location.href = `/recipes/${id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    saving.value = false;
  }
}
</script>

<template>
  <article>
    <p v-if="book"><a :href="`/sources/${book.id}`">← {{ book.title }}</a></p>
    <h1>{{ heading }}</h1>
    <p v-if="loadFailed" role="alert">This couldn't be loaded. Try reloading the page.</p>
    <form v-else-if="book" class="recipe-form" @submit.prevent="save">
      <label for="recipe-title">{{
        inFamily
          ? "Title, as your family calls it"
          : onWeb || inEpisode
            ? `Title, as the ${place} gives it`
            : `Title, as the ${place} prints it`
      }}</label>
      <input id="recipe-title" v-model="title" required maxlength="200" />

      <template v-if="onWeb">
        <label for="recipe-address">Web address of the recipe</label>
        <input
          id="recipe-address"
          v-model="webAddress"
          type="url"
          required
          maxlength="2000"
          :placeholder="book.host ? `https://${book.host}/…` : 'https://…'"
        />
        <p class="help">
          {{ book.host ? `A page on ${book.host}. ` : "The post's own address. " }}OpenLarder links to
          it; it never copies it.
        </p>
      </template>
      <template v-else-if="inIssue">
        <label for="recipe-issue">Issue, as the cover names it</label>
        <input
          id="recipe-issue"
          v-model="issue"
          list="known-issues"
          maxlength="200"
          :required="!issueDate"
          :placeholder="book.kind === 'newspaper' ? 'or leave blank and give the date' : 'May 2024'"
        />
        <datalist id="known-issues">
          <option v-for="i in book.issues" :key="i.id" :value="i.label" />
        </datalist>
        <label for="recipe-issue-date">Date of the issue (optional for a magazine)</label>
        <input id="recipe-issue-date" v-model="issueDate" type="date" class="page-input" />
        <label for="recipe-issue-page">Page</label>
        <input id="recipe-issue-page" v-model="issuePage" maxlength="20" class="page-input" placeholder="42" />
      </template>
      <template v-else-if="inEpisode">
        <p class="form-heading">{{ book.kind === "video_channel" ? "Which video" : "Which episode" }}</p>
        <p class="help">
          {{
            book.kind === "video_channel"
              ? "The video's address, and its title if you like."
              : "Its number, its title, or both."
          }}
        </p>
        <template v-if="book.kind !== 'video_channel'">
          <div class="episode-numbers">
            <span v-if="book.kind === 'tv_show'">
              <label for="recipe-season">Season</label>
              <input
                id="recipe-season"
                v-model="season"
                type="number"
                min="0"
                class="page-input"
              />
            </span>
            <span>
              <label for="recipe-episode-number">Episode</label>
              <input
                id="recipe-episode-number"
                v-model="episodeNumber"
                type="number"
                min="0"
                class="page-input"
                :required="season !== ''"
              />
            </span>
          </div>
        </template>
        <template v-if="book.kind !== 'tv_show'">
          <label for="recipe-episode-address">{{
            book.kind === "video_channel" ? "The video's address" : "Its address (optional)"
          }}</label>
          <input
            id="recipe-episode-address"
            v-model="episodeAddress"
            type="url"
            maxlength="2000"
            :required="book.kind === 'video_channel'"
            placeholder="https://…"
          />
        </template>
        <label for="recipe-episode-title">{{
          book.kind === "video_channel" ? "The video's title" : "The episode's title"
        }}</label>
        <input
          id="recipe-episode-title"
          v-model="episodeTitle"
          list="known-episodes"
          maxlength="200"
          :required="book.kind !== 'video_channel' && episodeNumber === '' && !episodeAddress"
        />
        <datalist id="known-episodes">
          <template v-for="e in book.episodes" :key="e.id">
            <option v-if="e.title" :value="e.title" />
          </template>
        </datalist>
        <label for="recipe-aired-on">When it aired (optional)</label>
        <input id="recipe-aired-on" v-model="airedOn" type="date" class="page-input" />
        <label for="recipe-at">Where in it the recipe starts (optional)</label>
        <input
          id="recipe-at"
          v-model="at"
          maxlength="8"
          class="page-input"
          placeholder="12:34"
          pattern="(\d{1,2}:)?\d{1,3}:[0-5]\d"
          title="Minutes and seconds, like 12:34, or 1:02:03"
        />
      </template>
      <template v-else-if="onPackaging || inFamily" />
      <fieldset v-else>
        <legend>Page</legend>
        <p class="help">Leave a page blank if you don't know it yet.</p>
        <div v-for="e in editions" :key="e.id" class="edition-row">
          <label v-if="editions.length > 1" class="check">
            <input v-model="e.included" type="checkbox" />
            {{ e.label }}
          </label>
          <span v-else class="only-edition">{{ e.label }}</span>
          <input
            v-model="e.page"
            :disabled="!e.included"
            :aria-label="`Page in ${e.label}`"
            class="page-input"
            maxlength="20"
            placeholder="112"
          />
        </div>
      </fieldset>

      <label for="recipe-ingredients">Ingredients, one per line, without amounts</label>
      <textarea
        id="recipe-ingredients"
        v-model="ingredients"
        rows="10"
        spellcheck="false"
        :placeholder="example"
        aria-describedby="recipe-ingredients-help"
      />
      <p id="recipe-ingredients-help" class="help">
        Just what goes in, as the {{ place }} names it: “rhubarb”, not “200g rhubarb”. Amounts
        and the method stay {{ onWeb || onPackaging ? `on the ${place}` : `in the ${place}` }}.
      </p>
      <ul v-if="reviews.length" class="line-hints" aria-live="polite">
        <li v-for="r in reviews" :key="`${r.index}:${r.line}`">
          <strong>{{ r.line }}</strong>: {{ r.review.problems.join(" ") }}
          <button
            v-if="r.review.suggestion"
            type="button"
            class="link"
            @click="fix(r.index, r.line, r.review.suggestion)"
          >
            Use “{{ r.review.suggestion }}”
          </button>
          <button
            v-else-if="r.review.remove"
            type="button"
            class="link"
            @click="fix(r.index, r.line, null)"
          >
            Remove it
          </button>
        </li>
      </ul>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" class="primary" :disabled="saving">
        {{ saving ? "Saving…" : "Save" }}
      </button>
    </form>
    <p v-else class="status">Loading…</p>
  </article>
</template>
