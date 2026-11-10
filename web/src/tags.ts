// Tags: course, cuisine, diet and technique, from a fixed list only admins
// add to (routers/tags.py). A source's tags are its recipes' too.

export type TagKind = "diet" | "course" | "cuisine" | "technique";

export interface Tag {
  id: string;
  kind: TagKind;
  name: string;
}

// On a recipe: set on its source rather than on it.
export interface RecipeTag extends Tag {
  from_source: boolean;
}

// The kinds in the order pages show them, as they're headed.
export const KINDS: { kind: TagKind; label: string }[] = [
  { kind: "diet", label: "Diet" },
  { kind: "course", label: "Course" },
  { kind: "cuisine", label: "Cuisine" },
  { kind: "technique", label: "Technique" },
];

async function send<T>(url: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "That didn't work.");
  return data as T;
}

export const listTags = () => send<Tag[]>("/api/tags", "GET");
export const addTag = (kind: TagKind, name: string) => send<Tag>("/api/tags", "POST", { kind, name });
// All of the recipe's own tags, or the source's: any left out are taken off.
export const setRecipeTags = (id: string, tags: string[]) =>
  send<RecipeTag[]>(`/api/recipes/${id}/tags`, "PUT", { tags });
export const setSourceTags = (id: string, tags: string[]) =>
  send<Tag[]>(`/api/sources/${id}/tags`, "PUT", { tags });
