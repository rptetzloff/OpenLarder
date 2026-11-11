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

export const FORMAT_NAMES = { print: "Print", ebook: "Ebook" } as const;

// Each shop's own words, once each, for the links shown.
export const notes = (links: BuyLink[]) => [
  ...new Set(links.map((l) => l.note).filter((n): n is string => !!n)),
];

// The link, saying which page it was clicked on: a path, nothing more.
export const buyHref = (link: BuyLink) =>
  `${link.url}?from=${encodeURIComponent(location.pathname)}`;

// What the FTC asks of an affiliate link: said plainly, beside it.
export const DISCLOSURE = "OpenLarder earns a commission if you buy through these links.";
