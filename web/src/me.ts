// What /api/auth/me returns. display_name is null until the person chooses
// one, which the app asks for before anything else.
export interface Me {
  id: string;
  display_name: string | null;
  suggested_name: string | null;
  account_url: string | null;
}

// Sends the chosen name; resolves to the updated account, or rejects with
// the server's reason ("That name is taken.") to show beside the field.
export async function saveDisplayName(name: string): Promise<Me> {
  const res = await fetch("/api/account/display-name", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: name }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail : "That didn't work. Try again.";
    throw new Error(detail);
  }
  return body as Me;
}
