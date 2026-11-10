// What local models suggest: what /api/suggestions returns, and deciding one.

export interface Side {
  id: string | null;
  name: string;
  recipes: number;
  exists: boolean;
}

export interface Suggestion {
  id: string;
  kind: "merge" | "parent" | "line_fix" | "tag";
  decision: string | null;
  keep: "a" | "b" | null;
  a: Side | null;
  b: Side | null;
  // tag: the recipe, and the tag for it.
  recipe: {
    id: string;
    title: string;
    chapter: string | null;
    source_id: string | null;
    source_title: string | null;
    exists: boolean;
  } | null;
  tag: { id: string; kind: string; name: string; exists: boolean; already: boolean } | null;
  reason: string | null;
  similarity: number | null;
  // merge-v2 on: the model's word for how sure it is.
  certainty: "certain" | "likely" | null;
  confidence: number | null;
  model: string;
  prompt_version: string;
  status: "open" | "accepted" | "dismissed";
  created_at: string;
  decided_at: string | null;
  actionable: boolean;
}

export interface SuggestionPage {
  suggestions: Suggestion[];
  open_by_kind: Record<string, number>;
  total: number;
}

export const KIND_LABELS: Record<string, string> = {
  merge: "Same ingredient",
  parent: "One under another",
  tag: "Tag a recipe",
  line_fix: "Line fix",
};

export async function fetchSuggestions(params: {
  state: "open" | "decided";
  kind?: string;
  offset?: number;
}): Promise<SuggestionPage> {
  const query = new URLSearchParams({ state: params.state });
  if (params.kind) query.set("kind", params.kind);
  if (params.offset) query.set("offset", String(params.offset));
  const res = await fetch(`/api/suggestions?${query}`);
  if (!res.ok) throw new Error("The suggestions couldn't be loaded.");
  return res.json();
}

// Accepts (with the name to keep, for a merge) or dismisses; resolves to the
// suggestion as it now stands, or rejects with the server's reason.
export async function decide(
  id: string,
  action: "accept" | "dismiss",
  keep?: "a" | "b",
): Promise<Suggestion> {
  const res = await fetch(`/api/suggestions/${id}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(keep ? { keep } : {}),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work.");
  return body;
}
