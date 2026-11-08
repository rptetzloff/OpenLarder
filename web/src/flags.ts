// Flagged recipes: what /api/flags returns, and dealing with a flag.

export interface Flag {
  id: string;
  kind: string;
  detail: string | null;
  created_at: string;
  resolved_at: string | null;
  resolution: "fixed" | "dismissed" | null;
  note: string | null;
  recipe: { id: string; title: string; source_id: string; source_title: string };
}

export interface FlagPage {
  flags: Flag[];
  open_by_kind: Record<string, number>;
  total: number;
}

export const KIND_LABELS: Record<string, string> = {
  duplicate_title: "Same title as another recipe",
  no_ingredients: "No ingredients",
  no_page: "No page",
  line_removed: "Line removed",
  line_fragment: "Fragment of a page reference",
  reference_page: "Reference to the wrong page",
  unknown_reference: "Reference to a missing recipe",
  usually_left_out: "Usually left out",
  line_detail: "Amount or prep in a line",
};

export async function fetchFlags(params: {
  scope: "all" | "mine";
  state: "open" | "dealt_with";
  kind?: string;
  offset?: number;
}): Promise<FlagPage> {
  const query = new URLSearchParams({ scope: params.scope, state: params.state });
  if (params.kind) query.set("kind", params.kind);
  if (params.offset) query.set("offset", String(params.offset));
  const res = await fetch(`/api/flags?${query}`);
  if (!res.ok) throw new Error("The flags couldn't be loaded.");
  return res.json();
}

export async function recipeFlags(recipeId: string): Promise<Flag[]> {
  const res = await fetch(`/api/recipes/${recipeId}/flags`);
  return res.ok ? res.json() : [];
}

// Marks a flag fixed, or dismisses it with a reason; resolves to the flag as
// it now stands, or rejects with the server's reason.
export async function resolveFlag(
  flagId: string,
  resolution: "fixed" | "dismissed",
  note?: string,
): Promise<Flag> {
  const res = await fetch(`/api/flags/${flagId}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resolution, note: note ?? null }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}
