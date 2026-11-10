// Requests for a book to be indexed (routers/book_requests.py): asking,
// voting, claiming; and, for admins, who may claim.

export type State = "open" | "claimed" | "done" | "declined";

export interface BookRequest {
  id: string;
  isbn13: string | null;
  title: string;
  author: string | null;
  note: string | null;
  source_id: string | null;
  status: State;
  votes: number;
  created_at: string;
  claimed_by: { id: string; name: string | null } | null;
  claimed_at: string | null;
  reason: string | null;
  voted: boolean;
  mine: boolean;
}

export interface RequestPage {
  requests: BookRequest[];
  counts: Partial<Record<State, number>>;
}

export interface Asked {
  outcome: "created" | "voted" | "already" | "in_catalog";
  request: BookRequest | null;
  source_id: string | null;
}

export interface Person {
  id: string;
  name: string | null;
  is_enterer: boolean;
  is_admin: boolean;
  claims: number;
}

async function send<T>(url: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const answer = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof answer.detail === "string" ? answer.detail : "That didn't work. Try again.");
  }
  return answer;
}

export const listRequests = (state: State | "mine", sort: "votes" | "new") =>
  send<RequestPage>(`/api/requests?state=${state}&sort=${sort}`, "GET");

export const askFor = (body: {
  isbn: string;
  title: string;
  author: string;
  note: string;
  website: string;
}) => send<Asked>("/api/requests", "POST", body);

export const act = (id: string, action: "vote" | "claim" | "release") =>
  send<BookRequest>(`/api/requests/${id}/${action}`, "POST");

export const markDone = (id: string) => send<BookRequest>(`/api/requests/${id}/done`, "POST", {});

export const decline = (id: string, reason: string) =>
  send<BookRequest>(`/api/requests/${id}/decline`, "POST", { reason });

export const findPeople = (q: string) =>
  send<Person[]>(`/api/admin/people?q=${encodeURIComponent(q)}`, "GET");

export const setEnterer = (id: string, is_enterer: boolean) =>
  send<Person>(`/api/admin/people/${id}/enterer`, "PUT", { is_enterer });
