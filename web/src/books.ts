// What /api/books returns, and adding a book by ISBN.

export interface BookSummary {
  id: string;
  title: string;
  subtitle: string | null;
  authors: string[];
  cover_url: string | null;
  editions: number;
}

export interface Edition {
  id: string;
  title: string | null;
  isbn13: string | null;
  publisher: string | null;
  published_year: number | null;
  cover_url: string | null;
  open_library_url: string | null;
}

export interface Book {
  id: string;
  title: string;
  subtitle: string | null;
  credits: { author_id: string; credited_as: string; role: string }[];
  editions: Edition[];
  // pages: one per edition it is in, newest first; null = not recorded.
  recipes: { id: string; title: string; pages: (string | null)[] }[];
}

// Resolves to the book's ID, whether it was added now or was already here
// (`existing`), or rejects with a reason to show beside the field.
export async function addByIsbn(isbn: string): Promise<{ id: string; existing: boolean }> {
  const res = await fetch("/api/books", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ isbn }),
  });
  const body = await res.json().catch(() => ({}));
  if (res.status === 201) return { id: body.id, existing: false };
  if (res.status === 409 && body.detail?.work_id) return { id: body.detail.work_id, existing: true };
  const detail = typeof body.detail === "string" ? body.detail : "That didn't work. Try again.";
  throw new Error(detail);
}
