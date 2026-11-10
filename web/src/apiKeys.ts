// API keys (routers/account.py): reading the public API at a higher rate.

export interface ApiKey {
  id: string;
  name: string;
  // The key's start, to tell keys apart; the key is shown only when made.
  prefix: string;
  created_at: string;
  last_used_at: string | null;
}

async function send<T>(url: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "That didn't work.");
  return data as T;
}

export const listKeys = () => send<ApiKey[]>("/api/account/keys", "GET");
// The key itself comes back this once.
export const makeKey = (name: string) =>
  send<ApiKey & { key: string }>("/api/account/keys", "POST", { name });
export const revokeKey = (id: string) => send<void>(`/api/account/keys/${id}`, "DELETE");
