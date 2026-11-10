// Admin monitoring (routers/monitoring.py): the API's outside callers, and
// buy-link clicks.

export interface Caller {
  caller: string;
  key_id: string | null;
  key_name: string | null;
  key_prefix: string | null;
  owner: string | null;
  network: string | null;
  requests: number;
  searches: number;
  refused: number;
  today: number;
  last_at: string;
}

export interface UsagePage {
  days: number;
  requests: number;
  refused: number;
  callers: Caller[];
}

export interface ClicksPage {
  days: number;
  clicks: number;
  shops: { retailer: string; label: string; clicks: number; last_7_days: number }[];
  books: { source_id: string; title: string; isbn13: string | null; clicks: number }[];
  pages: { page: string | null; clicks: number }[];
  by_day: { day: string; clicks: number }[];
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error("That couldn't be loaded. Try reloading the page.");
  return res.json();
}

export const apiUsage = (days: number) => get<UsagePage>(`/api/admin/api-usage?days=${days}`);
export const clickStats = (days: number) => get<ClicksPage>(`/api/admin/clicks?days=${days}`);

export async function revokeAnyKey(id: string): Promise<void> {
  const res = await fetch(`/api/admin/keys/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("That key couldn't be revoked.");
}
