<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import type { Book } from "../books";
import { checkLines, type LineReview, recipeLines, saveRecipe } from "../recipes";

// Entering a whole book (Ray's wireframe): a row per recipe, page, title and
// ingredients, each saving when you leave it, with the line checks under it.
const props = defineProps<{ id: string }>();

const book = ref<Book | null>(null);
const loadFailed = ref(false);
// Which edition the page column is for.
const editionId = ref("");

interface Row {
  key: number;
  // null until it's saved the first time.
  id: string | null;
  page: string;
  title: string;
  // The chapter it's in; a new row starts in the one above's, since books
  // go a chapter at a time.
  chapter: string;
  text: string;
  // What was last saved, to tell whether it needs saving again.
  saved: { page: string; title: string; chapter: string; text: string } | null;
  // The recipe's pages in every edition, kept when the row saves.
  editions: { edition_id: string; page: string | null }[];
  status: "idle" | "saving" | "saved" | "error";
  savedAt: string;
  error: string;
  // The lines' check, for the text it was given.
  reviews: LineReview[] | null;
  checked: string;
  // Check chips answered "it's new", by line.
  kept: Set<string>;
}

let nextKey = 0;
function newRow(fields: Partial<Row> = {}): Row {
  return {
    key: nextKey++,
    id: null,
    page: "",
    title: "",
    chapter: "",
    text: "",
    saved: null,
    editions: [],
    status: "idle",
    savedAt: "",
    error: "",
    reviews: null,
    checked: "",
    kept: new Set(),
    ...fields,
  };
}
const rows = ref<Row[]>([]);
const nextRow = () => newRow({ chapter: rows.value[rows.value.length - 1]?.chapter ?? "" });
// The chapters typed so far, offered as you type one.
const chapters = computed(() =>
  [...new Set(rows.value.map((r) => r.chapter.trim()).filter(Boolean))].sort(),
);

// Lines are separated by semicolons or new lines; shown joined by "; "
// unless one holds a semicolon of its own.
const split = (text: string) =>
  text
    .split(/;|\n/)
    .map((l) => l.trim())
    .filter(Boolean);
const join = (lines: string[]) => lines.join(lines.some((l) => l.includes(";")) ? "\n" : "; ");

const pageOf = (editions: Row["editions"]) =>
  editions.find((e) => e.edition_id === editionId.value)?.page ?? "";

onMounted(async () => {
  try {
    const res = await fetch(`/api/sources/${props.id}`);
    if (!res.ok) throw new Error();
    book.value = await res.json();
    document.title = `Enter a whole book · ${book.value!.title} · OpenLarder`;
    editionId.value = book.value!.editions[0]?.id ?? "";
    const lines = await recipeLines(props.id);
    rows.value = book.value!.recipes.map((r) => {
      const fields = {
        id: r.id,
        title: r.title,
        chapter: r.chapter ?? "",
        text: join(lines.get(r.id) ?? []),
        editions: r.editions,
        page: "",
      };
      fields.page = pageOf(r.editions);
      const saved = { page: fields.page, title: r.title, chapter: fields.chapter, text: fields.text };
      return newRow({ ...fields, saved });
    });
    rows.value.push(nextRow());
    // The saved rows' lines, checked a few at a time.
    for (let i = 0; i < rows.value.length; i += 8) {
      await Promise.all(rows.value.slice(i, i + 8).filter((r) => r.id).map(check));
    }
  } catch {
    loadFailed.value = true;
  }
});

function changeEdition() {
  for (const row of rows.value) {
    if (!row.id || dirty(row)) continue;
    row.page = pageOf(row.editions);
    row.saved = { page: row.page, title: row.title, chapter: row.chapter, text: row.text };
  }
}

const dirty = (row: Row) =>
  row.saved
    ? row.page !== row.saved.page ||
      row.title !== row.saved.title ||
      row.chapter !== row.saved.chapter ||
      row.text !== row.saved.text
    : !!(row.page.trim() || row.title.trim() || row.text.trim());
const blank = (row: Row) => !row.id && !row.page.trim() && !row.title.trim() && !row.text.trim();

async function check(row: Row) {
  const text = row.text;
  const lines = split(text);
  if (!lines.length) {
    row.reviews = [];
    row.checked = text;
    return;
  }
  try {
    const found = await checkLines(lines, { sourceId: props.id, recipeId: row.id ?? undefined });
    if (row.text !== text) return;
    row.reviews = found;
    row.checked = text;
  } catch {
    row.reviews = null;
  }
}

async function save(row: Row) {
  if (!dirty(row) || row.status === "saving") return;
  if (!row.title.trim()) {
    if (blank(row)) return;
    row.status = "error";
    row.error = "A title is needed.";
    return;
  }
  const sent = { page: row.page, title: row.title, chapter: row.chapter, text: row.text };
  const page = row.page.trim() || null;
  // A new recipe is in every edition, with its page in this one; a saved one
  // keeps its other editions' pages.
  const editions = row.id
    ? [
        ...row.editions.filter((e) => e.edition_id !== editionId.value),
        { edition_id: editionId.value, page },
      ]
    : book.value!.editions.map((e) => ({
        edition_id: e.id,
        page: e.id === editionId.value ? page : null,
      }));
  row.status = "saving";
  row.error = "";
  try {
    const id = await saveRecipe(
      {
        title: row.title,
        editions,
        chapter: row.chapter.trim() || null,
        ingredients: split(row.text),
      },
      row.id ? { recipeId: row.id } : { bookId: props.id },
    );
    row.id = id;
    row.editions = editions;
    row.saved = sent;
    row.status = "saved";
    row.savedAt = new Date().toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    await check(row);
    // Typed into again while it saved: save that too.
    if (dirty(row)) await save(row);
  } catch (e) {
    row.status = "error";
    row.error = e instanceof Error ? e.message : String(e);
  }
  if (rows.value[rows.value.length - 1] === row) rows.value.push(nextRow());
}

// A row saves when focus leaves it, not when it moves between its boxes.
function left(row: Row, event: FocusEvent) {
  const to = event.relatedTarget as Node | null;
  if (to && (event.currentTarget as HTMLElement).contains(to)) return;
  save(row);
}

const pageInputs = ref(new Map<number, HTMLInputElement>());

async function focusRow(index: number) {
  if (index >= rows.value.length) rows.value.push(nextRow());
  await nextTick();
  pageInputs.value.get(rows.value[index].key)?.focus();
}

// Enter in the ingredients saves the row and starts the next.
function enter(index: number, event: KeyboardEvent) {
  if (event.shiftKey) return;
  event.preventDefault();
  const shown = visible.value;
  const at = shown.indexOf(rows.value[index]);
  const next = shown[at + 1];
  focusRow(next ? rows.value.indexOf(next) : rows.value.length);
}

// Pasting several lines into a title box fills that many rows.
function pasteTitles(index: number, event: ClipboardEvent) {
  const pasted = event.clipboardData?.getData("text") ?? "";
  if (!pasted.includes("\n")) return;
  event.preventDefault();
  const titles = pasted.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  let at = index;
  for (const title of titles) {
    while (at < rows.value.length && rows.value[at].title.trim()) at++;
    if (at >= rows.value.length) rows.value.push(nextRow());
    rows.value[at].title = title;
    at++;
  }
  if (!blank(rows.value[rows.value.length - 1])) rows.value.push(nextRow());
}

function addTen() {
  const at = rows.value.length;
  for (let i = 0; i < 10; i++) rows.value.push(nextRow());
  focusRow(at);
}

// A line's check, as a chip under the row.
interface Chip {
  text: string;
  warn: boolean;
  line: string;
  fix?: { label: string; to: string | null };
  keep?: boolean;
}

function chips(row: Row): Chip[] {
  if (!row.reviews || row.checked !== row.text) return [];
  const lines = split(row.checked);
  const out: Chip[] = [];
  row.reviews.forEach((r, i) => {
    const line = lines[i];
    if (r.problems.length) {
      out.push(
        r.suggestion
          ? { text: `“${line}” → ${r.suggestion}?`, warn: true, line, fix: { label: "Fix", to: r.suggestion } }
          : { text: `“${line}”: ${r.problems.join(" ")}`, warn: true, line, fix: { label: "Remove", to: null } },
      );
      return;
    }
    if (r.options.length > 1) {
      out.push({
        text: `${r.options.length} options: ${r.options.map((o) => o.ingredient?.name ?? o.recipe?.name ?? o.name).join(", then ")}`,
        warn: false,
        line,
      });
      return;
    }
    const o = r.options[0];
    if (!o) return;
    if (o.page !== null) {
      out.push(
        o.recipe
          ? { text: `${o.recipe.name} → p. ${o.recipe_pages.join(" / ") || "?"}`, warn: false, line }
          : {
              text: `${o.name} (p. ${o.page}): ${o.page_used ? "no recipe of that name there" : "no recipe there yet"}`,
              warn: true,
              line,
            },
      );
    } else if (!o.ingredient && o.similar.length && !row.kept.has(line)) {
      out.push({
        text: `“${o.name}” → ${o.similar[0].name}?`,
        warn: true,
        line,
        fix: { label: "Use", to: o.similar[0].name },
        keep: true,
      });
    }
  });
  return out;
}

const rowChips = computed(() => new Map(rows.value.map((r) => [r.key, chips(r)])));
const checksOn = (row: Row) => rowChips.value.get(row.key)!.filter((c) => c.warn).length;

function summary(row: Row): string {
  const count = split(row.text).length;
  if (!count) return row.id ? "No ingredients yet" : "";
  if (!row.reviews || row.checked !== row.text) return `${count} ingredient${count === 1 ? "" : "s"}`;
  const matched = row.reviews.every((r) => !r.problems.length && r.options.every((o) => o.ingredient || o.recipe));
  return `${count} ingredient${count === 1 ? "" : "s"}${matched ? ", all matched" : ""}`;
}

async function apply(row: Row, chip: Chip) {
  const lines = split(row.text);
  const at = lines.indexOf(chip.line);
  if (at < 0 || !chip.fix) return;
  if (chip.fix.to === null) lines.splice(at, 1);
  else lines[at] = chip.fix.to;
  row.text = join(lines);
  await save(row);
}

function keep(row: Row, chip: Chip) {
  row.kept.add(chip.line);
}

// Showing every row or only those with checks; in page order or as entered.
const onlyChecks = ref(false);
const order = ref<"page" | "entered">("page");
const pageKey = (row: Row) => {
  const page = row.saved?.page ?? "";
  const n = parseInt(page, 10);
  return Number.isNaN(n) ? Infinity : n;
};
const visible = computed(() => {
  // Rows not yet saved stay at the bottom, where they were typed.
  const saved = rows.value.filter((r) => r.id);
  const fresh = rows.value.filter((r) => !r.id);
  if (order.value === "page") {
    saved.sort((a, b) => pageKey(a) - pageKey(b) || a.title.localeCompare(b.title));
  }
  const all = [...saved, ...fresh];
  return onlyChecks.value ? all.filter((r) => checksOn(r) || r.status === "error") : all;
});

// Saves what's left, then back to the book; a row that won't save keeps you
// here to see why.
async function finish() {
  for (const row of rows.value) await save(row);
  if (!rows.value.some((r) => r.status === "error")) location.href = `/sources/${props.id}`;
}

const entered = computed(() => rows.value.filter((r) => r.id).length);
const withChecks = computed(() => rows.value.filter((r) => checksOn(r)).length);
const saving = computed(() => rows.value.some((r) => r.status === "saving"));
const unsaved = computed(() => rows.value.filter((r) => dirty(r) && r.status !== "saving").length);
</script>

<template>
  <article class="wide bulk-entry">
    <p v-if="loadFailed" role="alert">This couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!book" class="status">Loading…</p>
    <template v-else>
      <nav class="crumbs" aria-label="Breadcrumb">
        <a href="/sources">Sources</a>
        <span aria-hidden="true">/</span>
        <a :href="`/sources/${book.id}`">{{ book.title }}</a>
        <span aria-hidden="true">/</span>
        <span aria-current="page">Enter a whole book</span>
      </nav>
      <div class="bulk-head">
        <div>
          <h1>Enter a whole book</h1>
          <p class="muted">
            {{ book.title }}<template v-for="c in book.credits" :key="c.author_id">
              · <a :href="`/authors/${c.author_id}`">{{ c.name }}</a></template
            >
          </p>
        </div>
        <div v-if="book.kind === 'book' && book.editable && book.editions.length" class="bulk-edition">
          <label for="bulk-edition">Pages are for</label>
          <select
            id="bulk-edition"
            v-model="editionId"
            :disabled="saving || unsaved > 0"
            @change="changeEdition"
          >
            <option v-for="e in book.editions" :key="e.id" :value="e.id">
              {{ [e.published_year, e.isbn13 && `ISBN ${e.isbn13}`, e.title].filter(Boolean).join(" · ") || "Edition" }}
            </option>
          </select>
        </div>
      </div>

      <p v-if="book.kind !== 'book' || !book.editions.length">
        Entering a whole book works for a book with an edition.
        <a :href="`/sources/${book.id}/recipes/new`">Add a recipe</a> instead.
      </p>
      <p v-else-if="!book.editable">Only an admin can add to this book.</p>
      <template v-else>
        <div class="bulk-progress" role="status">
          <span><strong>{{ entered }}</strong> recipe{{ entered === 1 ? "" : "s" }} entered</span>
          <span><strong>{{ withChecks }}</strong> row{{ withChecks === 1 ? "" : "s" }} with checks</span>
          <span>{{ saving ? "Saving…" : unsaved ? `${unsaved} not saved yet` : "All changes saved" }}</span>
        </div>
        <p class="help">
          Each row saves when you leave it. <strong>Tab</strong> moves across;
          <strong>Enter</strong> in the ingredients saves and starts the next row
          (<strong>Shift+Enter</strong> for a new line). Separate ingredients with
          <strong>;</strong> or a new line, and write a recipe printed elsewhere in the book as
          <strong>Name (p. 14)</strong>. Names only, no amounts.
        </p>
        <div class="table-head">
          <div class="bulk-filter" role="group" aria-label="Show">
            <button type="button" class="secondary" :aria-pressed="!onlyChecks" @click="onlyChecks = false">
              All rows
            </button>
            <button type="button" class="secondary" :aria-pressed="onlyChecks" @click="onlyChecks = true">
              Only rows with checks
            </button>
          </div>
          <div class="table-controls">
            <label for="bulk-sort">Sort</label>
            <select id="bulk-sort" v-model="order">
              <option value="page">Page order</option>
              <option value="entered">Order entered</option>
            </select>
          </div>
        </div>

        <datalist id="bulk-chapters">
          <option v-for="c in chapters" :key="c" :value="c" />
        </datalist>
        <div class="bulk-grid">
          <div class="bulk-row bulk-labels" aria-hidden="true">
            <span>Page</span><span>Recipe title and chapter</span><span>Ingredients</span
            ><span>Status</span>
          </div>
          <p v-if="!visible.length" class="bulk-empty">No rows have checks.</p>
          <div
            v-for="row in visible"
            :key="row.key"
            class="bulk-row"
            :class="{ 'has-checks': checksOn(row) || row.status === 'error', fresh: !row.id }"
            role="group"
            :aria-label="row.title || 'New row'"
            @focusout="left(row, $event)"
          >
            <input
              :ref="(el) => el && pageInputs.set(row.key, el as HTMLInputElement)"
              v-model="row.page"
              aria-label="Page"
              maxlength="20"
              placeholder="Page"
            />
            <div class="bulk-title">
              <input
                v-model="row.title"
                aria-label="Recipe title"
                maxlength="200"
                placeholder="Recipe title"
                @paste="pasteTitles(rows.indexOf(row), $event)"
              />
              <input
                v-model="row.chapter"
                class="bulk-chapter"
                aria-label="Chapter"
                maxlength="100"
                list="bulk-chapters"
                autocomplete="off"
                placeholder="Chapter"
              />
            </div>
            <div class="bulk-lines">
              <textarea
                v-model="row.text"
                aria-label="Ingredients"
                rows="2"
                spellcheck="false"
                placeholder="Ingredient; ingredient; Sub-recipe (p. 14)"
                @keydown.enter="enter(rows.indexOf(row), $event)"
              />
              <p v-if="summary(row)" class="bulk-summary">{{ summary(row) }}</p>
              <ul v-if="rowChips.get(row.key)!.length" class="bulk-chips">
                <li
                  v-for="(chip, n) in rowChips.get(row.key)"
                  :key="n"
                  :class="chip.warn ? 'tone-warn' : 'tone-info'"
                >
                  {{ chip.text }}
                  <button v-if="chip.fix" type="button" class="link" @click="apply(row, chip)">
                    {{ chip.fix.label }}
                  </button>
                  <button v-if="chip.keep" type="button" class="link" @click="keep(row, chip)">
                    It's new
                  </button>
                </li>
              </ul>
            </div>
            <p class="bulk-status" :class="{ error: row.status === 'error' }">
              <template v-if="row.status === 'saving'">Saving…</template>
              <template v-else-if="row.status === 'error'">{{ row.error }}</template>
              <template v-else-if="row.id">
                ✓ Saved<template v-if="row.savedAt">{{ " " + row.savedAt }}</template
                ><template v-if="checksOn(row)">
                  · <strong>{{ checksOn(row) }} check{{ checksOn(row) === 1 ? "" : "s" }}</strong></template
                >
              </template>
              <template v-else>New row</template>
            </p>
          </div>
        </div>

        <p class="line-add">
          <button type="button" class="secondary" @click="addTen">+ Add 10 rows</button>
          <span class="help">Pasting several lines into a title box fills that many rows.</span>
        </p>
        <div class="add-actions">
          <p class="help">
            {{
              book.private
                ? "Only you, and the groups you share it with, see these."
                : "Each row publishes as soon as it saves, as open data under the ODbL."
            }}
          </p>
          <button type="button" class="primary" :disabled="saving" @click="finish">Done for now</button>
        </div>
      </template>
    </template>
  </article>
</template>
