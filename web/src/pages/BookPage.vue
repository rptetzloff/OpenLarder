<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  type Book,
  issueName,
  KIND_NAMES,
  kindPlural,
  removeFamily,
  renameFamily,
} from "../books";
import { type GroupSummary, listGroups, shareCollection } from "../groups";
import OpenLibraryCheck from "../components/OpenLibraryCheck.vue";
import OpenLibraryLink from "../components/OpenLibraryLink.vue";
import type { Me } from "../me";

// A source's page, laid out from Ray's wireframe (2026-11-08): what it is,
// its editions (a book's), the ingredients it uses most, and its recipes as
// a table, filtered and sorted here.
const props = defineProps<{ id: string; user: Me | null | undefined }>();
const book = ref<Book | null>(null);
const missing = ref(false);
const failed = ref(false);

// Each name links to its author; a role other than author is said.
const credits = computed(() =>
  (book.value?.credits ?? []).map((c) => ({
    ...c,
    role: c.role === "author" ? "" : ` (${c.role})`,
  })),
);
const cover = computed(() => book.value?.editions.find((e) => e.cover_url)?.cover_url ?? null);
const isBook = computed(() => book.value?.kind === "book");

// The edition whose pages the table shows: the newest, until another is chosen.
const editionId = ref<string | null>(null);
const edition = computed(
  () => book.value?.editions.find((e) => e.id === editionId.value) ?? book.value?.editions[0],
);
function editionLabel(e: Book["editions"][number]) {
  return [e.published_year, e.isbn13 && `ISBN ${e.isbn13}`].filter(Boolean).join(" · ") || "Edition";
}

async function load() {
  try {
    const res = await fetch(`/api/sources/${props.id}`);
    if (res.status === 404 || res.status === 422) missing.value = true;
    else if (!res.ok) failed.value = true;
    else {
      book.value = await res.json();
      document.title = `${book.value!.title} · OpenLarder`;
    }
  } catch {
    failed.value = true;
  }
}

// The ingredients it uses most: a dozen, then all of them on request.
const allIngredients = ref(false);
const ingredients = computed(() =>
  allIngredients.value ? book.value!.ingredients : book.value!.ingredients.slice(0, 12),
);

// The recipe table: narrowed by title, in page or title order, and for a
// book with several editions, the ones not in this edition on request.
type Row = Book["recipes"][number];
const filter = ref("");
// One chapter, or all; the chapters in the book's order.
const chapter = ref("");
const order = ref<"page" | "title">("page");
const showAbsent = ref(false);
const pageIn = (r: Row) => r.editions.find((p) => p.edition_id === edition.value?.id);
const inEdition = (r: Row) => !isBook.value || !edition.value || !!pageIn(r);
const absent = computed(() => (book.value?.recipes ?? []).filter((r) => !inEdition(r)).length);
// Where a recipe is, as the table's first column says it.
function place(r: Row): string {
  if (isBook.value) {
    const here = pageIn(r);
    if (!here) return "Not in this edition";
    return here.page ?? "Not recorded";
  }
  if (r.issue) return `${issueName(r.issue)}${r.pages[0] ? `, p. ${r.pages[0]}` : ""}`;
  if (r.episode) return `${r.episode}${r.at ? `, at ${r.at}` : ""}`;
  return "";
}
const placeHeading = computed(() => {
  const kind = book.value?.kind ?? "";
  if (kind === "book") return "Page";
  if (kind === "magazine" || kind === "newspaper") return "Issue";
  if (["tv_show", "podcast", "video_channel"].includes(kind)) return "Episode";
  return "";
});
const naturally = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const rows = computed(() => {
  const words = filter.value.trim().toLowerCase();
  const list = (book.value?.recipes ?? []).filter(
    (r) =>
      (showAbsent.value || inEdition(r)) &&
      (!words || r.title.toLowerCase().includes(words)) &&
      (!chapter.value || r.chapter === chapter.value),
  );
  if (order.value === "title" || !placeHeading.value) return list;
  // Page order: recorded pages first, as numbers where they are numbers.
  const key = (r: Row) => (isBook.value ? (pageIn(r)?.page ?? null) : place(r) || null);
  return [...list].sort((a, b) => {
    const ka = key(a);
    const kb = key(b);
    if (ka === kb) return naturally.compare(a.title, b.title);
    if (ka === null) return 1;
    if (kb === null) return -1;
    return naturally.compare(ka, kb);
  });
});
// The book's chapters, in the order of their first recipe by page.
const chapters = computed(() => {
  const byPage = [...(book.value?.recipes ?? [])].sort((a, b) =>
    naturally.compare(pageIn(a)?.page ?? a.pages[0] ?? "~", pageIn(b)?.page ?? b.pages[0] ?? "~"),
  );
  return [...new Set(byPage.map((r) => r.chapter).filter((c): c is string => !!c))];
});
function lineSummary(r: Row) {
  const more = r.line_count - r.lines.length;
  return r.lines.join(", ") + (more > 0 ? `, +${more}` : "");
}

// A family collection's owner renames or deletes it here.
const newName = ref("");
const renaming = ref(false);
const actionError = ref("");
async function rename() {
  actionError.value = "";
  try {
    await renameFamily(book.value!.id, newName.value);
    renaming.value = false;
    await load();
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : String(e);
  }
}
async function remove() {
  const count = book.value!.recipes.length;
  const recipes = count === 1 ? "its recipe" : `its ${count} recipes`;
  if (!confirm(`Delete ${book.value!.title} and ${recipes}? This can't be undone.`)) return;
  try {
    await removeFamily(book.value!.id);
    location.href = "/sources";
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : String(e);
  }
}

// Its owner picks which of their groups see it.
const myGroups = ref<GroupSummary[] | null>(null);
const sharing = ref<string[]>([]);
const shareNote = ref("");
async function loadSharing() {
  if (!book.value?.manageable || !book.value.private) return;
  sharing.value = book.value.shared_with.map((g) => g.id);
  myGroups.value = await listGroups().catch(() => []);
}
async function saveSharing() {
  shareNote.value = "";
  actionError.value = "";
  try {
    book.value!.shared_with = await shareCollection(book.value!.id, sharing.value);
    shareNote.value = "Saved.";
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : String(e);
  }
}
const sharedNames = computed(() => (book.value?.shared_with ?? []).map((g) => g.name).join(", "));
const adminTools = computed(() => !!props.user?.is_admin && book.value?.kind !== "family");

onMounted(async () => {
  await load();
  await loadSharing();
});
</script>

<template>
  <article class="wide source-page">
    <p v-if="missing">There's nothing here. It may have been removed, or the link is wrong.</p>
    <p v-else-if="failed" role="alert">This couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!book" class="status">Loading…</p>
    <template v-else>
      <Teleport v-if="adminTools" to="#admin-bar" defer>
        <div class="admin-bar">
          <div class="bar">
            <strong>Admin</strong>
            <a :href="`/sources/${book.id}/edit`">Edit {{ KIND_NAMES[book.kind] }}</a>
            <a v-if="isBook" href="#open-library">
              {{ book.open_library_url ? "Check Open Library" : "Link to Open Library" }}
            </a>
            <a href="/admin/flags">Flagged recipes</a>
          </div>
        </div>
      </Teleport>

      <nav class="crumbs" aria-label="Breadcrumb">
        <a href="/sources">Sources</a>
        <span aria-hidden="true">/</span>
        <span>{{ kindPlural(book.kind) }}</span>
        <span aria-hidden="true">/</span>
        <span aria-current="page">{{ book.title }}</span>
      </nav>

      <div class="source-head">
        <img v-if="cover" :src="cover" :alt="`Cover of ${book.title}`" class="source-cover" />
        <div v-else class="source-cover" aria-hidden="true"></div>
        <div class="source-about">
          <p class="kind">{{ KIND_NAMES[book.kind] }}</p>
          <h1>{{ book.title }}</h1>
          <p v-if="book.subtitle" class="subtitle">{{ book.subtitle }}</p>
          <p v-if="credits.length" class="credits">
            <template v-for="(c, i) in credits" :key="i"
              ><template v-if="i > 0">, </template
              ><a :href="`/authors/${c.author_id}`">{{ c.credited_as }}</a>{{ c.role }}</template
            >
          </p>
          <p v-if="book.private && book.manageable" class="byline">
            A private family collection: only you{{
              sharedNames ? ` and ${sharedNames}` : ""
            }}
            see it.
          </p>
          <p v-else-if="book.private" class="byline">
            {{ book.owner_name ?? "Someone" }}'s private family collection, shared with you
            through {{ sharedNames }}.
          </p>
          <ul class="tags">
            <li>
              {{ book.recipes.length.toLocaleString() }}
              {{ book.recipes.length === 1 ? "recipe" : "recipes" }} indexed
            </li>
            <li v-if="book.paywalled">Subscription site</li>
          </ul>
          <p class="actions">
            <a
              v-if="book.recipes.length"
              :href="`/search?source=${book.id}`"
              class="button-outline"
              >Search in this {{ KIND_NAMES[book.kind] }}</a
            >
            <a
              v-if="book.editable"
              :href="`/sources/${book.id}/recipes/new`"
              class="button-outline"
              >Add a recipe</a
            >
            <a
              v-if="book.editable && isBook"
              :href="`/sources/${book.id}/bulk`"
              class="button-outline"
              >Enter a whole book</a
            >
          </p>
          <template v-if="book.manageable">
            <form v-if="renaming" class="inline-form" @submit.prevent="rename">
              <label for="family-rename" class="visually-hidden">New name</label>
              <input id="family-rename" v-model="newName" required maxlength="300" />
              <button type="submit" class="primary">Rename</button>
              <button type="button" class="link" @click="renaming = false">Cancel</button>
            </form>
            <p v-else class="byline">
              <button
                type="button"
                class="link"
                @click="
                  newName = book.title;
                  renaming = true;
                "
              >
                Rename</button
              >&nbsp;
              <button type="button" class="link" @click="remove">Delete</button>
            </p>
            <p v-if="actionError" class="error" role="alert">{{ actionError }}</p>
          </template>
        </div>
        <aside v-if="book.open_library_url || book.host" class="source-elsewhere">
          <h2>Elsewhere</h2>
          <p v-if="book.host">
            <a :href="`https://${book.host}`" rel="nofollow noopener">{{ book.host }}</a>
          </p>
          <p v-if="book.open_library_url">
            <a :href="book.open_library_url">See it on Open Library</a>
          </p>
        </aside>
      </div>

      <section v-if="isBook && book.editions.length" class="source-section">
        <h2>Edition</h2>
        <div class="edition-tabs" role="group" aria-label="Editions">
          <button
            v-for="e in book.editions"
            :key="e.id"
            type="button"
            :aria-pressed="e.id === edition?.id"
            @click="editionId = e.id"
          >
            {{ editionLabel(e) }}
          </button>
        </div>
        <dl v-if="edition" class="edition-facts">
          <div>
            <dt>Publisher</dt>
            <dd>{{ edition.publisher ?? "Not recorded" }}</dd>
          </div>
          <div>
            <dt>Published</dt>
            <dd>{{ edition.published_year ?? "Not recorded" }}</dd>
          </div>
          <div>
            <dt>ISBN-13</dt>
            <dd>{{ edition.isbn13 ?? "None" }}</dd>
          </div>
          <div v-if="edition.open_library_url">
            <dt>Open Library</dt>
            <dd><a :href="edition.open_library_url">This edition</a></dd>
          </div>
        </dl>
      </section>

      <section v-if="book.ingredients.length" class="source-section">
        <h2>Most-used ingredients</h2>
        <p class="status">
          The {{ book.ingredients.length }} its recipes use most. Each opens a search within the
          {{ KIND_NAMES[book.kind] }}.
        </p>
        <ul class="ingredient-chips">
          <li v-for="i in ingredients" :key="i.id">
            <a :href="`/search?source=${book.id}&i=${i.id}`">{{ i.name }}</a>
            <span class="count">{{ i.recipes }}</span>
          </li>
          <li v-if="book.ingredients.length > 12">
            <button type="button" class="chip-toggle" @click="allIngredients = !allIngredients">
              {{ allIngredients ? "Show fewer" : `Show all ${book.ingredients.length}` }}
            </button>
          </li>
        </ul>
      </section>

      <section v-if="book.manageable && book.private && myGroups" class="source-section">
        <h2>Shared with</h2>
        <form v-if="myGroups.length" class="recipe-form" @submit.prevent="saveSharing">
          <label v-for="g in myGroups" :key="g.id" class="check"
            ><input v-model="sharing" type="checkbox" :value="g.id" /> {{ g.name }}</label
          >
          <p class="help">
            Everyone in a ticked group sees this collection; its editors and admins can add and
            change recipes. Only you can rename, delete or share it.
          </p>
          <button type="submit" class="primary">Save</button>
          <p v-if="shareNote" class="status" role="status">{{ shareNote }}</p>
        </form>
        <p v-else class="status">
          To share it with your family, <a href="/groups">make a group</a> and invite them.
        </p>
      </section>

      <section class="source-section">
        <div class="table-head">
          <h2>{{ isBook && book.editions.length > 1 ? "Recipes in this edition" : "Recipes" }}</h2>
          <div v-if="book.recipes.length" class="table-controls">
            <label for="recipe-filter" class="visually-hidden">Filter by title</label>
            <input
              id="recipe-filter"
              v-model="filter"
              type="search"
              autocomplete="off"
              placeholder="Filter by title"
            />
            <template v-if="chapters.length">
              <label for="recipe-chapter" class="visually-hidden">Chapter</label>
              <select id="recipe-chapter" v-model="chapter">
                <option value="">All chapters</option>
                <option v-for="c in chapters" :key="c" :value="c">{{ c }}</option>
              </select>
            </template>
            <template v-if="placeHeading">
              <label for="recipe-order" class="visually-hidden">Order</label>
              <select id="recipe-order" v-model="order">
                <option value="page">{{ placeHeading }} order</option>
                <option value="title">Title order</option>
              </select>
            </template>
          </div>
        </div>
        <table v-if="rows.length" class="recipe-table">
          <thead>
            <tr>
              <th v-if="placeHeading" scope="col">{{ placeHeading }}</th>
              <th scope="col">Recipe</th>
              <th scope="col">Ingredients</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.id">
              <td v-if="placeHeading" :class="{ muted: isBook && !pageIn(r)?.page }">
                {{ place(r) }}
              </td>
              <td>
                <a :href="`/recipes/${r.id}`">{{ r.title }}</a>
                <span v-if="r.component" class="badge">Component</span>
                <div v-if="r.chapter && !chapter" class="muted chapter-note">{{ r.chapter }}</div>
              </td>
              <td class="lines">{{ lineSummary(r) || "None recorded yet" }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else-if="book.recipes.length" class="status">
          No recipe here matches{{ filter ? ` “${filter}”` : "" }}{{ chapter ? ` in “${chapter}”` : "" }}.
        </p>
        <p v-else class="status">No recipes indexed yet.</p>
        <div v-if="isBook && book.editions.length > 1" class="table-foot">
          <p class="status">
            Pages are for the selected edition. “Not recorded” means it's in this edition but the
            page isn't known yet.
          </p>
          <button v-if="absent" type="button" class="link" @click="showAbsent = !showAbsent">
            {{
              showAbsent
                ? "Hide the recipes not in this edition"
                : `Show ${absent} ${absent === 1 ? "recipe" : "recipes"} not in this edition`
            }}
          </button>
        </div>
      </section>

      <section v-if="adminTools && isBook" id="open-library" class="source-section">
        <OpenLibraryLink v-if="!book.open_library_url" :book="book" />
        <OpenLibraryCheck v-else :book-id="book.id" @taken="load" />
      </section>

      <!-- Open Library asks for a courtesy link back where its data is shown. -->
      <p v-if="isBook" class="status credit-line">
        Book details and covers from <a href="https://openlibrary.org">Open Library</a>.
      </p>
    </template>
  </article>
</template>
