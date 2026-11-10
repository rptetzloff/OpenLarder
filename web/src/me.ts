export type Role = "user" | "contributor" | "moderator" | "admin" | "owner";

export const ROLE_LABELS: Record<Role, string> = {
  user: "User",
  contributor: "Contributor",
  moderator: "Moderator",
  admin: "Administrator",
  owner: "Owner",
};

// What /api/auth/me returns. display_name is null until the person chooses
// one, which the app asks for before anything else.
export interface Me {
  id: string;
  display_name: string | null;
  suggested_name: string | null;
  account_url: string | null;
  // Their role, and what it lets them do (roles.py): edit the catalog
  // (moderator up), run the site (administrator up), claim requests
  // (contributor up), and the roles they may give or take away.
  role: Role;
  may_edit: boolean;
  may_run: boolean;
  may_claim: boolean;
  grants: Role[];
  // Whether they've accepted the contributor agreement as it reads now,
  // which adding to the catalog needs (agreement.py).
  agreed: boolean;
  // Their buy-link shops (shops.ts); null until chosen.
  shops: { order: string[]; hidden: string[] } | null;
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
