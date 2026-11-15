// Producers (producers.py): farms, mills and makers that sell ingredients
// themselves. Each link goes through OpenLarder's own /go/producer/ address,
// which counts the click and sends it on. *Ray, 2026-11-13.*

export interface ProducerCard {
  key: string;
  label: string;
  description: string | null;
  // What a new customer gets, if anything.
  offer: string | null;
  // "Ships to 30 states", or "Ships everywhere".
  ships: string;
  earns: "affiliate" | "referral" | "none";
  // What is earned and by whom, said beside the link wherever it is.
  disclosure: string;
  url: string;
}

// As the Producers page has it: with what it supplies, and where it ships.
export interface Producer extends ProducerCard {
  supplies: { id: string; name: string }[];
  // The states' names; empty when it ships everywhere.
  states: string[];
}

export async function listProducers(): Promise<Producer[]> {
  const res = await fetch("/api/producers");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// The link, saying which page it was clicked on: a path, nothing more.
export const visitHref = (p: ProducerCard) =>
  `${p.url}?from=${encodeURIComponent(location.pathname)}`;
