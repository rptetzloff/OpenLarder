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
