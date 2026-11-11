// Reports: "Report a problem" on a public record, and the moderators' queue
// (routers/reports.py).

export type Kind = "recipe" | "source" | "ingredient" | "author";
export type Reason = "wrong" | "duplicate" | "copied" | "spam" | "other";

export const REASONS: { reason: Reason; label: string }[] = [
  { reason: "wrong", label: "Something's wrong (a page, a title, an ingredient)" },
  { reason: "duplicate", label: "It's here twice" },
  { reason: "copied", label: "It copies text it shouldn't (a method, a headnote)" },
  { reason: "spam", label: "Spam, or not a real record" },
  { reason: "other", label: "Something else" },
];

export interface Report {
  id: string;
  kind: Kind;
  target_id: string;
  title: string | null;
  href: string | null;
  reason: Reason;
  note: string | null;
  by: string | null;
  status: "open" | "resolved" | "dismissed";
  resolution: string | null;
  created_at: string;
  others: number;
}

async function send<T>(url: string, method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const answer = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof answer.detail === "string" ? answer.detail : "That didn't send. Try again.");
  }
  return answer as T;
}

export const sendReport = (body: {
  kind: Kind;
  id: string;
  reason: Reason;
  note: string;
  website: string;
}) => send<void>("/api/reports", "POST", body);

export const reportQueue = (state: "open" | "resolved" | "dismissed") =>
  send<{ reports: Report[]; counts: Record<string, number> }>(`/api/admin/reports?state=${state}`);

export const decideReport = (id: string, action: "resolve" | "dismiss", note: string) =>
  send<void>(`/api/admin/reports/${id}`, "POST", { action, note: note || null });
