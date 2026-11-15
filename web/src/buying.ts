// Buy links (buying.py): where to buy an edition, through OpenLarder's own
// /go/ address, which counts the click and sends it on with the affiliate ID.

export interface BuyLink {
  retailer: string;
  label: string;
  url: string;
  // What the shop's programme asks to be said beside its link (Amazon's).
  note: string | null;
  format: "print" | "ebook";
}

// The shop's name, saying so when it's the ebook.
export const shopName = (link: BuyLink) =>
  link.format === "ebook" ? `${link.label} (ebook)` : link.label;

// A format as a heading over its shops on a book's page, and as said in a
// link's name there ("Buy the print book at Bookshop.org"). Ray's round 5
// list, item 7, 2026-11-15: the format was a word on each button, and
// "Print" on a button read as printing the page.
export const FORMAT_HEADINGS = { print: "Print book", ebook: "Ebook" } as const;
export const FORMAT_SAID = { print: "print book", ebook: "ebook" } as const;

// The links under their formats. A format comes where its first shop does
// in the order given, which is the reader's, and one with no shop isn't
// there at all.
export function byFormat(links: BuyLink[]): { format: BuyLink["format"]; links: BuyLink[] }[] {
  const formats = [...new Set(links.map((l) => l.format))];
  return formats.map((format) => ({ format, links: links.filter((l) => l.format === format) }));
}

// Each shop's own words, once each, for the links shown.
export const notes = (links: BuyLink[]) => [
  ...new Set(links.map((l) => l.note).filter((n): n is string => !!n)),
];

// The link, saying which page it was clicked on: a path, nothing more.
export const buyHref = (link: BuyLink) =>
  `${link.url}?from=${encodeURIComponent(location.pathname)}`;

// What the FTC asks of an affiliate link: said plainly, beside it. Under
// the buy buttons on a book's page and on a recipe's, which says it again
// in its own words under its ingredients' Shop links. "May earn", as the
// recipe's page and the terms had it and the round 5 drawing has for both:
// until 2026-11-15 a book's page said "earns", which isn't so of a shop
// with no affiliate ID set.
export const DISCLOSURE = "OpenLarder may earn a commission if you buy through these links.";
