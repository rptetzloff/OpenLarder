<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import AgreementPanel from "../components/AgreementPanel.vue";
import { type Book, issueName, KIND_NAMES, SHOWS } from "../books";
import type { Me } from "../me";
import {
  checkLines,
  type LineOption,
  type LineReview,
  proposeChange,
  type Recipe,
  saveRecipe,
} from "../recipes";

// New when bookId is given, editing when recipeId is. Ray's wireframe: four
// steps, the source, the recipe and where it is, its ingredients, then a
// look over it all before saving.
// With propose, the edit is sent as a suggestion for a moderator to apply
// (routers/proposals.py), for a contributor and a published recipe.
const props = defineProps<{
  bookId?: string;
  recipeId?: string;
  user?: Me | null;
  propose?: boolean;
}>();
// Why, for the moderator, when suggesting.
const reason = ref("");

const book = ref<Book | null>(null);
// The agreement accepted on this page, before the app knows.
const accepted = ref(false);
const title = ref("");
// The chapter or section it's in, as the book names it; the ones this
// source has already are offered as you type.
const chapter = ref("");
const chapters = computed(() =>
  [...new Set((book.value?.recipes ?? []).map((r) => r.chapter).filter(Boolean))].sort(),
);
// The title as saved, for the breadcrumbs while it's being changed.
const savedTitle = ref("");
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

// The summary's "Book: …".
const kindName = computed(() => {
  const name = KIND_NAMES[book.value?.kind ?? ""] ?? "source";
  return name[0].toUpperCase() + name.slice(1);
});
const heading = computed(() =>
  props.propose ? "Suggest a change" : props.recipeId ? "Change a recipe" : "Add a recipe",
);

function label(e: { title: string | null; published_year: number | null; isbn13: string | null }) {
  return [e.title ?? book.value?.title, e.published_year, e.isbn13 && `ISBN ${e.isbn13}`]
    .filter(Boolean)
    .join(" · ");
}

// The ingredient lines, a box each; key keeps the boxes apart as lines come
// and go.
interface Row {
  key: number;
  text: string;
}
let nextKey = 0;
const newRow = (text = ""): Row => ({ key: nextKey++, text });
const rows = ref<Row[]>([newRow()]);
const lines = computed(() => rows.value.map((r) => r.text));

// The steps. Each one reached stays open to go back to.
const step = ref(2);
const reached = ref(2);
const steps = computed(() => [
  "Source",
  onPackaging.value || inFamily.value
    ? "Recipe"
    : `Recipe and ${onWeb.value ? "address" : inIssue.value ? "issue" : inEpisode.value ? "episode" : "page"}`,
  "Ingredients",
  "Review and save",
]);
const stepHeading = ref<HTMLElement | null>(null);

async function go(to: number) {
  step.value = to;
  reached.value = Math.max(reached.value, to);
  // Where the new step starts, for a screen reader and the keyboard.
  await nextTick();
  stepHeading.value?.focus();
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
      title.value = savedTitle.value = existing.title;
      chapter.value = existing.chapter ?? "";
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
      rows.value = [...existing.ingredients.map((t) => newRow(t)), newRow()];
      // Changing one usually means its ingredients.
      step.value = 3;
      reached.value = 4;
    }
    document.title = `${heading.value} · ${book.value!.title} · OpenLarder`;
  } catch {
    loadFailed.value = true;
  }
});

// Where the recipe is, as the summary says it.
const where = computed(() => {
  if (onWeb.value) return webAddress.value || "No address yet";
  if (inIssue.value) {
    const which = issue.value ? issueName(issue.value) : issueDate.value && issueName(issueDate.value);
    return [which, issuePage.value && `p. ${issuePage.value}`].filter(Boolean).join(", ") || "No issue yet";
  }
  if (inEpisode.value) {
    const which = [
      season.value !== "" && `Season ${season.value}`,
      episodeNumber.value !== "" && `episode ${episodeNumber.value}`,
      episodeTitle.value && `“${episodeTitle.value}”`,
      !episodeTitle.value && episodeAddress.value,
    ].filter(Boolean);
    return [which.join(", "), at.value && `at ${at.value}`].filter(Boolean).join(" ") || "No episode yet";
  }
  if (onPackaging.value) return "On the packaging";
  if (inFamily.value) return "In the family's copy";
  const inIt = editions.value.filter((e) => e.included);
  if (!inIt.length) return "In no edition";
  return inIt
    .map((e) => `${editions.value.length > 1 ? `${e.label}: ` : ""}${e.page ? `p. ${e.page}` : "page not recorded"}`)
    .join(" · ");
});

// The entry rules and what each line will be matched to, checked as the
// lines are typed (issue #26). Advice only: a line can be an exception, so
// saving never waits on it. Kept by row, with the text it was given for, so
// a row typed into since shows nothing rather than an old answer.
const reviews = ref(new Map<number, { text: string; review: LineReview }>());
let asked = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
watch(
  [lines, book],
  () => {
    if (!book.value) return;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const mine = ++asked;
      const sent = rows.value.map((r) => ({ key: r.key, text: r.text }));
      try {
        const found = await checkLines(
          sent.map((r) => r.text),
          { sourceId: book.value!.id, recipeId: props.recipeId },
        );
        if (mine !== asked) return;
        reviews.value = new Map(sent.map((r, i) => [r.key, { text: r.text, review: found[i] }]));
      } catch {
        if (mine === asked) reviews.value = new Map();
      }
    }, 400);
  },
  { deep: true },
);

// Hints someone has answered "keep it" to, by row, for the text they kept.
const kept = ref(new Map<number, string>());

type Tone = "ok" | "info" | "warn";
interface Hint {
  tone: Tone;
  text: string;
  review: LineReview;
}

function hintFor(row: Row): Hint | null {
  const found = reviews.value.get(row.key);
  if (!row.text.trim() || !found || found.text !== row.text) return null;
  const review = found.review;
  if (review.problems.length) {
    if (kept.value.get(row.key) === row.text && !review.refused) return null;
    return { tone: "warn", text: review.problems.join(" "), review };
  }
  const options = review.options;
  if (!options.length) return null;
  if (options.length > 1) {
    return { tone: "ok", text: `${options.length} options, in the ${place.value}'s order`, review };
  }
  const only = options[0];
  if (only.page !== null) {
    return only.recipe
      ? {
          tone: "info",
          text: `Recipe here: ${only.recipe.name}${only.recipe_pages.length ? `, p. ${only.recipe_pages.join(" / ")}` : ""}`,
          review,
        }
      : {
          tone: "warn",
          text: only.page_used
            ? `Not linked: p. ${only.page} has no recipe of that name.`
            : `No recipe on p. ${only.page} yet; it links when one is added.`,
          review,
        };
  }
  if (only.ingredient) {
    return {
      tone: "ok",
      text: `Matched: ${only.ingredient.name}${only.alias ? " (another name for it)" : ""}`,
      review,
    };
  }
  if (kept.value.get(row.key) === row.text) {
    return { tone: "ok", text: "New ingredient", review };
  }
  return { tone: "warn", text: "No exact match", review };
}

// How an option of a line with several reads.
function optionText(o: LineOption): string {
  if (o.page !== null) return o.recipe ? `${o.recipe.name} (recipe here)` : `${o.name} (p. ${o.page})`;
  return o.ingredient ? o.ingredient.name : `${o.name} (new)`;
}

const hints = computed(() => rows.value.map((r) => hintFor(r)));
const checksLeft = computed(() => hints.value.filter((h) => h?.tone === "warn").length);
// Lines saving would refuse, which do stop it.
const refusedLeft = computed(() => hints.value.filter((h) => h?.review.refused).length);

const rowInputs = ref<HTMLInputElement[]>([]);

async function focusRow(index: number) {
  await nextTick();
  rowInputs.value[index]?.focus();
}

function addRow(after = rows.value.length - 1) {
  rows.value.splice(after + 1, 0, newRow());
  focusRow(after + 1);
}

function removeRow(index: number) {
  rows.value.splice(index, 1);
  if (!rows.value.length) rows.value.push(newRow());
  focusRow(Math.min(index, rows.value.length - 1));
}

function replace(index: number, text: string) {
  rows.value[index].text = text;
}

// Pasting several lines into a box fills that many.
function paste(index: number, event: ClipboardEvent) {
  const pasted = event.clipboardData?.getData("text") ?? "";
  if (!pasted.includes("\n")) return;
  event.preventDefault();
  const found = pasted.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!found.length) return;
  const row = rows.value[index];
  const added = row.text.trim() ? found : found.slice(1);
  if (!row.text.trim()) row.text = found[0];
  rows.value.splice(index + 1, 0, ...added.map((t) => newRow(t)));
  focusRow(index + added.length);
}

const filled = computed(() => rows.value.filter((r) => r.text.trim()));

async function save(another = false) {
  saving.value = true;
  error.value = "";
  try {
    const body = {
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
        chapter: chapter.value.trim() || null,
        ingredients: lines.value,
    };
    if (props.propose && props.recipeId) {
      await proposeChange(props.recipeId, { ...body, reason: reason.value.trim() || null });
      location.href = `/recipes/${props.recipeId}?proposed=1`;
      return;
    }
    const id = await saveRecipe(
      body,
      props.recipeId ? { recipeId: props.recipeId } : { bookId: book.value!.id },
    );
    location.href = another ? `/sources/${book.value!.id}/recipes/new` : `/recipes/${id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    saving.value = false;
  }
}
</script>

<template>
  <article class="wide add-recipe">
    <nav v-if="book" class="crumbs" aria-label="Breadcrumb">
      <a href="/sources">Sources</a>
      <span aria-hidden="true">/</span>
      <a :href="`/sources/${book.id}`">{{ book.title }}</a>
      <template v-if="recipeId">
        <span aria-hidden="true">/</span>
        <a :href="`/recipes/${recipeId}`">{{ savedTitle }}</a>
      </template>
      <span aria-hidden="true">/</span>
      <span aria-current="page">{{ propose ? "Suggest a change" : recipeId ? "Change" : "Add a recipe" }}</span>
    </nav>
    <h1>{{ heading }}</h1>
    <p class="muted">Where it is and what goes in it. No amounts, method or headnotes.</p>
    <p v-if="loadFailed" role="alert">This couldn't be loaded. Try reloading the page.</p>
    <!-- Outside a family collection, adding to the catalog needs the agreement. -->
    <AgreementPanel
      v-else-if="book && !inFamily && user && !user.agreed && !accepted"
      :agreed="false"
      @accepted="accepted = true"
    />
    <template v-else-if="book">
      <p v-if="!inFamily && user && !user.may_edit && !user.trusted && !propose" class="muted">
        What you add waits for a moderator's review before anyone else sees it.
      </p>
      <ol class="steps" aria-label="Steps">
        <li v-for="(name, i) in steps" :key="i">
          <button
            type="button"
            class="step"
            :aria-current="step === i + 1 ? 'step' : undefined"
            :disabled="i + 1 > reached"
            @click="go(i + 1)"
          >
            {{ i + 1 }} · {{ name
            }}<template v-if="i + 1 < reached && step !== i + 1"
              ><span aria-hidden="true"> ✓</span><span class="visually-hidden"> (done)</span></template
            >
          </button>
        </li>
      </ol>

      <div class="add-layout" :class="{ solo: !user?.may_edit }">
        <div>
          <div v-if="step > 2" class="add-summary">
            <dl>
              <div>
                <dt>Source</dt>
                <dd>{{ kindName }}: {{ book.title }}</dd>
              </div>
              <div>
                <dt>Recipe</dt>
                <dd>{{ title }}</dd>
              </div>
              <div v-if="chapter.trim()">
                <dt>Chapter</dt>
                <dd>{{ chapter }}</dd>
              </div>
              <div>
                <dt>Where</dt>
                <dd>{{ where }}</dd>
              </div>
            </dl>
            <button type="button" class="secondary small" @click="go(2)">Change</button>
          </div>

          <section v-if="step === 1" aria-labelledby="step-heading">
            <h2 id="step-heading" ref="stepHeading" tabindex="-1">Source</h2>
            <p>
              This recipe goes in <a :href="`/sources/${book.id}`">{{ book.title }}</a>, a
              {{ KIND_NAMES[book.kind] ?? "source" }}.
              <template v-if="!recipeId">
                To add one somewhere else, find it under <a href="/sources">Sources</a> and choose
                Add a recipe there.
              </template>
            </p>
            <button type="button" class="primary" @click="go(2)">Next</button>
          </section>

          <form
            v-else-if="step === 2"
            class="recipe-form"
            aria-labelledby="step-heading"
            @submit.prevent="go(3)"
          >
            <h2 id="step-heading" ref="stepHeading" tabindex="-1">{{ steps[1] }}</h2>
            <label for="recipe-title">{{
              inFamily
                ? "Title, as your family calls it"
                : onWeb || inEpisode
                  ? `Title, as the ${place} gives it`
                  : `Title, as the ${place} prints it`
            }}</label>
            <input id="recipe-title" v-model="title" required maxlength="200" />
            <template v-if="!onWeb && !inEpisode">
              <label for="recipe-chapter">Chapter or section (optional)</label>
              <input
                id="recipe-chapter"
                v-model="chapter"
                maxlength="100"
                list="recipe-chapters"
                autocomplete="off"
                :placeholder="chapters[0] ?? 'Yeast Breads'"
              />
              <datalist id="recipe-chapters">
                <option v-for="c in chapters" :key="c!" :value="c!" />
              </datalist>
            </template>

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
                {{ book.host ? `A page on ${book.host}. ` : "The post's own address. " }}OpenLarder
                links to it; it never copies it.
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
              <input
                id="recipe-issue-page"
                v-model="issuePage"
                maxlength="20"
                class="page-input"
                placeholder="42"
              />
            </template>
            <template v-else-if="inEpisode">
              <p class="form-heading">
                {{ book.kind === "video_channel" ? "Which video" : "Which episode" }}
              </p>
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
            <button type="submit" class="primary">Next</button>
          </form>

          <form v-else-if="step === 3" aria-labelledby="step-heading" @submit.prevent="go(4)">
            <h2 id="step-heading" ref="stepHeading" tabindex="-1">Ingredients</h2>
            <p class="help">
              Name each one as the {{ place }} does: “rhubarb”, not “200g rhubarb”. Amounts and the
              method stay {{ onWeb || onPackaging ? `on the ${place}` : `in the ${place}` }}. Checks
              show beside a line as you type and never stop you saving. A recipe printed elsewhere in
              it is written as its name and page: “Biscuit Blend (p. 14)”.
            </p>
            <ol class="line-rows">
              <li v-for="(row, i) in rows" :key="row.key" class="line-row">
                <div class="line-main">
                  <div class="line-input">
                    <input
                      :ref="(el) => (rowInputs[i] = el as HTMLInputElement)"
                      v-model="row.text"
                      :aria-label="`Ingredient ${i + 1}`"
                      :aria-describedby="hints[i] ? `line-hint-${row.key}` : undefined"
                      maxlength="150"
                      spellcheck="false"
                      :placeholder="i === 0 ? 'rhubarb' : ''"
                      @keydown.enter.prevent="addRow(i)"
                      @paste="paste(i, $event)"
                    />
                    <button
                      v-if="rows.length > 1"
                      type="button"
                      class="remove"
                      :aria-label="`Remove ingredient ${i + 1}`"
                      title="Remove"
                      @click="removeRow(i)"
                    >
                      ×
                    </button>
                  </div>
                  <p
                    v-if="hints[i]"
                    :id="`line-hint-${row.key}`"
                    class="line-tag"
                    :class="`tone-${hints[i]!.tone}`"
                  >
                    {{ hints[i]!.text }}
                  </p>
                </div>
                <template v-if="hints[i]">
                  <ol v-if="hints[i]!.review.options.length > 1" class="line-options">
                    <li v-for="(o, n) in hints[i]!.review.options" :key="n">
                      {{ optionText(o) }}
                      <span class="muted">· {{ n === 0 ? "first choice" : "or this" }}</span>
                    </li>
                  </ol>
                  <div v-if="hints[i]!.tone === 'warn'" class="line-actions">
                    <template v-if="hints[i]!.review.suggestion">
                      <button
                        type="button"
                        class="secondary small"
                        @click="replace(i, hints[i]!.review.suggestion!)"
                      >
                        Change to “{{ hints[i]!.review.suggestion }}”
                      </button>
                      <button
                        v-if="!hints[i]!.review.refused"
                        type="button"
                        class="secondary small"
                        @click="kept.set(row.key, row.text)"
                      >
                        Keep as typed
                      </button>
                      <span v-else>Saving refuses an amount with a unit.</span>
                    </template>
                    <template v-else-if="hints[i]!.review.remove">
                      <button type="button" class="secondary small" @click="removeRow(i)">
                        Remove
                      </button>
                      <button type="button" class="secondary small" @click="kept.set(row.key, row.text)">
                        Keep: it matters here
                      </button>
                    </template>
                    <template v-else-if="hints[i]!.review.options[0]?.page === null">
                      <template v-if="hints[i]!.review.options[0].similar.length">
                        <span>Did you mean</span>
                        <button
                          v-for="s in hints[i]!.review.options[0].similar"
                          :key="s.id"
                          type="button"
                          class="secondary small"
                          @click="replace(i, s.name)"
                        >
                          {{ s.name }}
                        </button>
                      </template>
                      <button type="button" class="secondary small" @click="kept.set(row.key, row.text)">
                        It's new
                      </button>
                    </template>
                  </div>
                </template>
              </li>
            </ol>
            <p class="line-add">
              <button type="button" class="secondary" @click="addRow()">+ Add ingredient</button>
              <span class="help">Enter starts a new line; pasting several lines fills that many.</span>
            </p>
            <button type="submit" class="primary">Next</button>
          </form>

          <section v-else aria-labelledby="step-heading">
            <h2 id="step-heading" ref="stepHeading" tabindex="-1">Review and save</h2>
            <p v-if="!filled.length" class="muted">
              No ingredients yet. It saves without them, and is flagged until they're added.
            </p>
            <template v-else>
              <h3 class="review-heading">
                {{ filled.length }} ingredient{{ filled.length === 1 ? "" : "s" }}
              </h3>
              <ol class="review-lines">
                <li v-for="row in filled" :key="row.key">{{ row.text.trim() }}</li>
              </ol>
              <p v-if="refusedLeft" class="muted">
                {{ refusedLeft }} line{{ refusedLeft === 1 ? " starts" : "s start" }} with an amount,
                which saving refuses.
                <button type="button" class="secondary small" @click="go(3)">Fix them</button>
              </p>
              <p v-else-if="checksLeft" class="muted">
                {{ checksLeft }} line{{ checksLeft === 1 ? " has" : "s have" }} a check on
                {{ checksLeft === 1 ? "it" : "them" }}; they save as typed.
                <button type="button" class="secondary small" @click="go(3)">Look again</button>
              </p>
            </template>
            <template v-if="propose">
              <label for="propose-reason" class="form-heading">Why (optional)</label>
              <textarea
                id="propose-reason"
                v-model="reason"
                rows="2"
                maxlength="500"
                placeholder="It's on page 14 in my copy"
              ></textarea>
            </template>
            <div class="add-actions">
              <p v-if="error" class="error" role="alert">{{ error }}</p>
              <button type="button" class="primary" :disabled="saving" @click="save()">
                {{
                  propose
                    ? saving
                      ? "Sending…"
                      : "Send the suggestion"
                    : saving
                      ? "Saving…"
                      : "Save"
                }}
              </button>
              <button
                v-if="!recipeId"
                type="button"
                class="secondary"
                :disabled="saving"
                @click="save(true)"
              >
                Save and add another
              </button>
              <p class="help">
                {{
                  propose
                    ? "A moderator looks at it beside the recipe as it is, and applies it or says why not."
                    : book.private
                      ? "Only you, and the groups you share it with, see it."
                      : !inFamily && !user?.may_edit && !user?.trusted
                        ? "It waits for a moderator's review, then publishes as open data under the ODbL."
                        : "It publishes as soon as it's saved, as open data under the ODbL."
                }}
              </p>
            </div>
          </section>
        </div>

        <aside v-if="user?.may_edit" class="add-aside" aria-label="Other ways to add">
          <div v-if="book.kind === 'book' && !recipeId" class="aside-card">
            <h2>Enter a whole book</h2>
            <p>One row per recipe: page, title, ingredients. Each row saves as you go.</p>
            <a :href="`/sources/${book.id}/bulk`" class="primary">Open bulk entry</a>
          </div>
          <div class="aside-card">
            <h2>Bulk import</h2>
            <p>
              Upload a list of sources and their recipes. Every line is kept; anything doubtful is
              flagged on its recipe.
            </p>
            <a href="/admin/import" class="primary">Open bulk import</a>
            <p><a href="/admin/imports">Import history</a></p>
          </div>
        </aside>
      </div>
    </template>
    <p v-else class="status">Loading…</p>
  </article>
</template>
