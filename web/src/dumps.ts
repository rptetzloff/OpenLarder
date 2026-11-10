// The weekly ODbL data dumps (routers/dumps.py).

export interface Dump {
  built_at: string;
  csv_url: string;
  csv_bytes: number;
  json_url: string;
  json_bytes: number;
  counts: Record<string, number>;
}

export interface Dumps {
  available: boolean;
  licence_url: string;
  attribution: string;
  latest: Dump | null;
  older: Dump[];
}

export async function listDumps(): Promise<Dumps> {
  const res = await fetch("/api/dumps");
  if (!res.ok) throw new Error("The downloads couldn't be loaded. Try reloading the page.");
  return res.json();
}

export async function buildDump(): Promise<Dump> {
  const res = await fetch("/api/admin/dumps", { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}

export const size = (bytes: number) =>
  bytes < 1_000_000 ? `${Math.max(1, Math.round(bytes / 1000))} kB` : `${(bytes / 1_000_000).toFixed(1)} MB`;
