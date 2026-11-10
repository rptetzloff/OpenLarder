// Review (routers/review.py): a contributor's books and recipes wait for a
// moderator; the contributor agreement comes first.

export type Review = "published" | "pending" | "returned";

export interface Item {
  id: string;
  title: string;
  review: Review;
  review_note: string | null;
  by: string | null;
  created_at: string;
}

export interface Group {
  source: Item;
  kind: string;
  recipes: Item[];
}

export interface Agreement {
  version: string;
  points: string[];
}

async function send<T>(url: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const answer = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof answer.detail === "string" ? answer.detail : "That didn't work. Try again.");
  }
  return answer as T;
}

export const reviewQueue = () => send<{ groups: Group[]; pending: number }>("/api/review");

export const decide = (what: "sources" | "recipes", id: string, action: "approve" | "return", note?: string) =>
  send<Item>(`/api/review/${what}/${id}`, "POST", { action, note: note ?? null });

export const approveAll = (sourceId: string) =>
  send<{ source: boolean; recipes: number }>(`/api/review/sources/${sourceId}/approve-all`, "POST");

export const myContributions = () => send<Group[]>("/api/account/contributions");

export const readAgreement = () => send<Agreement>("/api/agreement");

export const acceptAgreement = (version: string) =>
  send<void>("/api/account/agreement", "POST", { version });

// How a state reads beside what's in it.
export const REVIEW_LABELS: Record<Review, string> = {
  published: "Published",
  pending: "Waiting for review",
  returned: "Sent back",
};
