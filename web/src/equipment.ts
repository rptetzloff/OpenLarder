// Equipment: what /api/equipment returns (routers/equipment.py).

export interface Related {
  id: string;
  name: string;
}

export interface EquipmentSummary {
  id: string;
  name: string;
  // Expected in any kitchen, so no recipe lists it.
  assumed: boolean;
  // Recipes recorded as needing exactly this.
  recipes: number;
  // What it counts as, which can be several, and its other names.
  counts_as: Related[];
  aliases: string[];
}

export interface EquipmentList {
  equipment: EquipmentSummary[];
  total: number;
}

export interface Equipment {
  id: string;
  name: string;
  assumed: boolean;
  aliases: Related[];
  // A stand mixer counts as a mixer, and a mixer includes a stand mixer.
  counts_as: Related[];
  includes: Related[];
  // Recipes needing exactly this; and it or anything that counts as it.
  total: number;
  family_total: number;
}

// sort "name": A to Z, rather than most needed first; assumed: what any
// kitchen has too.
export async function listEquipment(
  q: string,
  offset = 0,
  options: { sort?: "uses" | "name"; assumed?: boolean } = {},
): Promise<EquipmentList> {
  const query = new URLSearchParams({ q });
  if (offset) query.set("offset", String(offset));
  if (options.sort === "name") query.set("sort", "name");
  if (options.assumed) query.set("assumed", "true");
  const res = await fetch(`/api/equipment?${query}`);
  if (!res.ok) throw new Error("The equipment couldn't be loaded.");
  return res.json();
}

// null: there's none with this id.
export async function fetchEquipment(id: string): Promise<Equipment | null> {
  const res = await fetch(`/api/equipment/${id}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("This equipment couldn't be loaded.");
  return res.json();
}

// Changing the list, for moderators (routers/equipment.py).

// A name another thing has, or is also called: the page offers to merge.
export class Taken extends Error {
  constructor(
    message: string,
    readonly equipment: Related,
  ) {
    super(message);
  }
}

async function send(path: string, method: string, body?: unknown) {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const out = res.status === 204 ? {} : await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = out.detail;
    if (detail?.equipment) throw new Taken(detail.message, detail.equipment);
    throw new Error(typeof detail === "string" ? detail : "That didn't work. Try again.");
  }
  return out;
}

export async function addEquipment(name: string, assumed: boolean): Promise<Related> {
  return send("/api/equipment", "POST", { name, assumed });
}

export async function renameEquipment(id: string, name: string): Promise<Related> {
  return send(`/api/equipment/${id}`, "PATCH", { name });
}

// Whether any kitchen has it. Refused for one a recipe lists.
export async function setAssumed(id: string, assumed: boolean): Promise<Related> {
  return send(`/api/equipment/${id}/assumed`, "PUT", { assumed });
}

// Resolves to the thing that's left.
export async function mergeEquipment(id: string, into: string): Promise<Related> {
  return send(`/api/equipment/${id}/merge`, "POST", { into });
}

export async function deleteEquipment(id: string): Promise<void> {
  await send(`/api/equipment/${id}`, "DELETE");
}

export async function addAlias(id: string, name: string): Promise<Related> {
  return send(`/api/equipment/${id}/aliases`, "POST", { name });
}

export async function deleteAlias(id: string, aliasId: string): Promise<void> {
  await send(`/api/equipment/${id}/aliases/${aliasId}`, "DELETE");
}

// A thing can count as several: this adds one, and the next takes one away.
export async function countAs(id: string, broader: string): Promise<Related> {
  return send(`/api/equipment/${id}/counts-as/${broader}`, "PUT");
}

export async function stopCountingAs(id: string, broader: string): Promise<void> {
  await send(`/api/equipment/${id}/counts-as/${broader}`, "DELETE");
}
