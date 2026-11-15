// Finished searches to try, under "Cook with what you have" on the front
// page and on Search before anything is asked (Ray's cleanup pass, section
// 11; his round 4 wireframes, 2026-11-14): well-used ingredients, so each
// finds plenty. Checked against the catalog on 2026-11-12: at least twenty
// recipes use all three of each. One shows only when every ingredient of it
// is in the catalog.
import { ingredientsNamed } from "./ingredients";

const EXAMPLES = [
  ["chicken", "lemon", "garlic"],
  ["egg", "butter", "flour"],
  ["onion", "olive oil", "tomato"],
  ["carrot", "onion", "celery"],
];

export interface Example {
  label: string;
  href: string;
}

export async function findExamples(): Promise<Example[]> {
  const found = await ingredientsNamed([...new Set(EXAMPLES.flat())]).catch(() => []);
  const ids = new Map(found.map((i) => [i.name.toLowerCase(), i.id]));
  return EXAMPLES.filter((names) => names.every((n) => ids.has(n))).map((names) => ({
    label: names.join(" + "),
    href: `/search?${new URLSearchParams(names.map((n) => ["i", ids.get(n)!]))}`,
  }));
}
