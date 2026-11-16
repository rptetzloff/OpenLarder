// Equipment: what /api/equipment returns (routers/equipment.py).

import type { Listed } from "./ingredients";

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
  // A page of the recipes that need it, each with how the need reads
  // there; and how many that list holds in all.
  recipes: (Listed & { line: string | null })[];
  listed_total: number;
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

// null: there's none with this id. under: list the recipes needing
// anything that counts as it too.
export async function fetchEquipment(
  id: string,
  offset = 0,
  under = false,
): Promise<Equipment | null> {
  const query = new URLSearchParams();
  if (offset) query.set("offset", String(offset));
  if (under) query.set("under", "true");
  const res = await fetch(`/api/equipment/${id}?${query}`);
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

// A need as saving would read it, to say before it's saved: what each thing
// typed will be matched to; with none, the things named like it (it's a new
// thing unless one of them is meant); and why saving would refuse it, if it
// would. As an ingredient line's review is (recipes.ts).
export interface NeedOption {
  name: string;
  equipment: Related | null;
  alias: boolean;
  similar: Related[];
}

export interface NeedRead {
  detail: string | null;
  options: NeedOption[];
  problem: string | null;
}

// A need with something else in place of what was typed, keeping its size:
// "9-inch springfrm pan" taken as Springform pan is "9-inch Springform pan".
export const needNamed = (read: NeedRead, name: string) =>
  read.detail ? `${read.detail} ${name}` : name;

// A row's needs typed into one cell (entering a whole book): each as the
// server parted them, with its reading.
export interface CellRead {
  // "none" alone.
  nothing_special: boolean;
  needs: (NeedRead & { text: string })[];
}

export async function checkCell(cell: string): Promise<CellRead> {
  const res = await fetch("/api/equipment/check-cell", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cell }),
  });
  if (!res.ok) throw new Error("The equipment couldn't be checked.");
  return res.json();
}

export async function checkNeeds(needs: string[]): Promise<NeedRead[]> {
  const res = await fetch("/api/equipment/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ needs }),
  });
  if (!res.ok) throw new Error("The equipment couldn't be checked.");
  return res.json();
}
