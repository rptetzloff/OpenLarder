<script setup lang="ts">
import { computed, ref } from "vue";
import type { Me } from "../me";
import {
  BATCH,
  addBook,
  addRunLines,
  finishRun,
  importBatch,
  startRun,
  parseFiles,
  type Parsed,
  type ReportLine,
  reportCsv,
} from "../importing";

defineProps<{ user: Me | null | undefined }>();
document.title = "Import · Admin · OpenLarder";

const booksFile = ref<File | null>(null);
const recipesFile = ref<File | null>(null);
const parsed = ref<Parsed | null>(null);
const error = ref("");
const busy = ref(false);
const stage = ref<"pick" | "review" | "running" | "done">("pick");
const progress = ref({ books: 0, recipes: 0 });
const totals = ref({ created: 0, skipped: 0, errors: 0, flags: 0, booksFailed: 0, booksAdded: 0, booksExisting: 0 });
const runId = ref<string | null>(null);
const report = ref<ReportLine[]>([]);

const withIsbn = computed(() => parsed.value?.books.filter((b) => b.isbn13).length ?? 0);
const recipeTotal = computed(() => parsed.value?.recipes.length ?? 0);

const KINDS: Record<string, string> = {
  duplicate_title: "Same title on another page",
  no_ingredients: "No ingredients",
  no_page: "No page",
  line_removed: "Line removed",
  line_fragment: "Fragment of a page reference",
};

async function read() {
  if (!booksFile.value || !recipesFile.value) return;
  busy.value = true;
  error.value = "";
  try {
    parsed.value = await parseFiles(await booksFile.value.text(), await recipesFile.value.text());
    stage.value = "review";
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function run() {
  const p = parsed.value!;
  stage.value = "running";
  try {
    runId.value = await startRun(p.books.length, p.recipes.length, p.untitled_rows);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    stage.value = "review";
    return;
  }
  report.value = p.untitled_rows.map((row) => ({
    row,
    book: "",
    recipe: "",
    kind: "Not imported",
    detail: "No title or no book on this row",
  }));

  // Books first, one at a time: each is an Open Library lookup, and the
  // server paces those to Open Library's limits.
  const works = new Map<string, { id: string; isbn13: string | null }>();
  for (const book of p.books) {
    try {
      const { id, how } = await addBook(book);
      works.set(book.source_title.toLowerCase(), { id, isbn13: book.isbn13 });
      if (how === "already here") totals.value.booksExisting++;
      else totals.value.booksAdded++;
    } catch (e) {
      totals.value.booksFailed++;
      const detail = e instanceof Error ? e.message : String(e);
      report.value.push({ row: null, book: book.source_title, recipe: "", kind: "Book not added", detail });
      await addRunLines(runId.value!, [{ row: null, book: book.source_title, recipe: "", kind: "book_not_added", detail }]);
    }
    progress.value.books++;
  }

  const placed = [];
  for (const r of p.recipes) {
    const work = works.get(r.source.toLowerCase());
    if (!work) {
      totals.value.errors++;
      report.value.push({ row: r.row, book: r.source, recipe: r.title, kind: "Not imported", detail: "Its book isn't in the book list, or wasn't added" });
      progress.value.recipes++;
      continue;
    }
    placed.push({ ...r, work_id: work.id, isbn13: work.isbn13 });
  }
  const byRow = new Map(p.recipes.map((r) => [r.row, r]));
  for (let i = 0; i < placed.length; i += BATCH) {
    const batch = placed.slice(i, i + BATCH);
    try {
      const result = await importBatch(
        runId.value,
        batch.map((r) => ({
          row: r.row,
          work_id: r.work_id,
          isbn13: r.isbn13,
          title: r.title,
          page: r.page,
          ingredients: r.ingredients,
        })),
      );
      totals.value.created += result.created;
      totals.value.skipped += result.skipped;
      totals.value.errors += result.errors.length;
      totals.value.flags += result.flags.length;
      for (const e of result.errors) {
        const r = byRow.get(e.row);
        report.value.push({ row: e.row, book: r?.source ?? "", recipe: r?.title ?? "", kind: "Not imported", detail: e.reason });
      }
      for (const f of result.flags) {
        const r = byRow.get(f.row);
        report.value.push({ row: f.row, book: r?.source ?? "", recipe: r?.title ?? "", kind: KINDS[f.kind] ?? f.kind, detail: f.detail ?? "" });
      }
    } catch (e) {
      // A failed batch stops the run; importing again skips what got in.
      error.value = `${e instanceof Error ? e.message : String(e)} Run the import again to carry on: recipes already imported are skipped.`;
      break;
    }
    progress.value.recipes += batch.length;
  }
  const unplaced = report.value
    .filter((l) => l.kind === "Not imported" && l.row !== null && !p.untitled_rows.includes(l.row) && l.detail.startsWith("Its book isn't in the book list"))
    .map((l) => ({ row: l.row, book: l.book, recipe: l.recipe, kind: "not_imported" as const, detail: l.detail }));
  if (unplaced.length) await addRunLines(runId.value!, unplaced);
  await finishRun(runId.value!, {
    books_added: totals.value.booksAdded,
    books_existing: totals.value.booksExisting,
    books_failed: totals.value.booksFailed,
  });
  stage.value = "done";
}

function download() {
  const blob = new Blob([reportCsv(report.value)], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "openlarder-import-report.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}
</script>

<template>
  <article>
    <p><a href="/admin">← Admin</a></p>
    <h1>Import</h1>
    <p v-if="!user?.is_admin" class="status">Only an admin can import.</p>

    <template v-else-if="stage === 'pick'">
      <p>
        Choose the book list and the recipe list. Nothing is stored until you've seen what's in
        them.
      </p>
      <form class="recipe-form" @submit.prevent="read">
        <label for="books-file">Book list (CSV)</label>
        <input id="books-file" type="file" accept=".csv,text/csv" required @change="booksFile = ($event.target as HTMLInputElement).files?.[0] ?? null" />
        <label for="recipes-file">Recipe list (CSV)</label>
        <input id="recipes-file" type="file" accept=".csv,text/csv" required @change="recipesFile = ($event.target as HTMLInputElement).files?.[0] ?? null" />
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button type="submit" class="primary" :disabled="busy">{{ busy ? "Reading…" : "Read the files" }}</button>
      </form>
    </template>

    <template v-else-if="stage === 'review' && parsed">
      <ul>
        <li>{{ parsed.books.length }} books: {{ withIsbn }} with an ISBN, looked up on Open Library; {{ parsed.books.length - withIsbn }} without, added from the list.</li>
        <li>{{ recipeTotal.toLocaleString() }} recipes.</li>
        <li v-if="parsed.blank_rows">{{ parsed.blank_rows }} blank rows, skipped.</li>
        <li v-if="parsed.untitled_rows.length">{{ parsed.untitled_rows.length }} rows with no title or no book, which can't be imported; they'll be in the report.</li>
        <li v-if="parsed.unknown_sources.length">
          Recipes name {{ parsed.unknown_sources.length }} books that aren't in the book list:
          {{ parsed.unknown_sources.slice(0, 10).join(", ")
          }}{{ parsed.unknown_sources.length > 10 ? `, and ${parsed.unknown_sources.length - 10} more` : "" }}.
          Their recipes won't be imported.
        </li>
      </ul>
      <p class="status">
        Books take a few minutes, paced for Open Library. Recipes publish at once; anything doubtful
        is flagged on its recipe. Running the import again skips what it already added.
      </p>
      <button type="button" class="primary" @click="run">Import</button>
    </template>

    <template v-else-if="parsed">
      <p role="status">
        Books: {{ progress.books }} of {{ parsed.books.length }} ·
        Recipes: {{ progress.recipes.toLocaleString() }} of {{ recipeTotal.toLocaleString() }}
      </p>
      <progress :value="progress.books + progress.recipes" :max="parsed.books.length + recipeTotal" />
      <template v-if="stage === 'done'">
        <h2>Done</h2>
        <ul>
          <li>{{ totals.created.toLocaleString() }} recipes added, {{ totals.skipped.toLocaleString() }} already there.</li>
          <li>{{ totals.flags.toLocaleString() }} flags raised, to look at in the report.</li>
          <li v-if="totals.errors">{{ totals.errors.toLocaleString() }} recipes not imported.</li>
          <li v-if="totals.booksFailed">{{ totals.booksFailed }} books not added.</li>
        </ul>
        <button v-if="report.length" type="button" class="primary" @click="download">Download the report (CSV)</button>
        <p>This run, and its report, are kept in the <a href="/admin/imports">import history</a>.</p>
      </template>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </template>
  </article>
</template>
