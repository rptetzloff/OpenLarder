// Driving a bulk import from the browser, in short requests: read both
// files, add each book, then send recipes in batches. See importer.py.

export interface ParsedBook {
  source_title: string;
  authors: string[];
  isbn13: string | null;
  year: number | null;
  recipes: number;
}

export interface ParsedRecipe {
  row: number;
  source: string;
  title: string;
  page: string | null;
  ingredients: string[];
}

export interface Parsed {
  books: ParsedBook[];
  recipes: ParsedRecipe[];
  blank_rows: number;
  untitled_rows: number[];
  unknown_sources: string[];
}

export interface ReportLine {
  row: number | null;
  book: string;
  recipe: string;
  kind: string;
  detail: string;
}

export const BATCH = 200;

async function post(url: string, body: unknown): Promise<{ status: number; body: any }> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: res.status, body: await res.json().catch(() => ({})) };
}

function reason(body: any, fallback: string): string {
  if (typeof body?.detail === "string") return body.detail;
  if (typeof body?.detail?.message === "string") return body.detail.message;
  return fallback;
}

export async function parseFiles(booksCsv: string, recipesCsv: string): Promise<Parsed> {
  const { status, body } = await post("/api/import/parse", {
    books_csv: booksCsv,
    recipes_csv: recipesCsv,
  });
  if (status !== 200) throw new Error(reason(body, "Those files couldn't be read."));
  return body as Parsed;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Adds one book and resolves to its work ID: by ISBN through Open Library,
// or from the list's own title and authors when it has no ISBN or Open
// Library doesn't know it. Already in the catalog counts as success.
export async function addBook(book: ParsedBook): Promise<{ id: string; how: string }> {
  if (book.isbn13) {
    for (let attempt = 1; attempt <= 3; attempt++) {
      const { status, body } = await post("/api/books", { isbn: book.isbn13 });
      if (status === 201) return { id: body.id, how: "added from Open Library" };
      if (status === 409 && body.detail?.work_id) return { id: body.detail.work_id, how: "already here" };
      if (status === 404) break; // not on Open Library: fall back to the list's details
      if (status !== 502) throw new Error(reason(body, `Adding it failed (${status}).`));
      await sleep(2000 * attempt); // Open Library didn't answer; give it a moment
    }
  }
  const { status, body } = await post("/api/books/manual", {
    title: book.source_title,
    authors: book.authors,
    year: book.year,
  });
  if (status !== 200) throw new Error(reason(body, `Adding it failed (${status}).`));
  return { id: body.id, how: body.existing ? "already here" : "added from the book list" };
}

export async function importBatch(
  items: {
    row: number;
    work_id: string;
    isbn13: string | null;
    title: string;
    page: string | null;
    ingredients: string[];
  }[],
): Promise<{
  created: number;
  skipped: number;
  errors: { row: number; reason: string }[];
  flags: { row: number; recipe_id: string; kind: string; detail: string | null }[];
}> {
  const { status, body } = await post("/api/import/recipes", { items });
  if (status !== 200) throw new Error(reason(body, `A batch failed (${status}).`));
  return body;
}

// A CSV of everything worth a look, quoted so commas and quotes survive.
export function reportCsv(lines: ReportLine[]): string {
  const cell = (v: string | number | null) => `"${String(v ?? "").replaceAll('"', '""')}"`;
  const header = ["Row", "Book", "Recipe", "What", "Detail"].map(cell).join(",");
  return [header, ...lines.map((l) => [l.row, l.book, l.recipe, l.kind, l.detail].map(cell).join(","))].join("\r\n");
}
