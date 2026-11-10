// Buy links (buying.py): where to buy an edition, through OpenLarder's own
// /go/ address, which counts the click and sends it on with the affiliate ID.

export interface BuyLink {
  retailer: string;
  label: string;
  url: string;
}

// The link, saying which page it was clicked on: a path, nothing more.
export const buyHref = (link: BuyLink) =>
  `${link.url}?from=${encodeURIComponent(location.pathname)}`;

// What the FTC asks of an affiliate link: said plainly, beside it.
export const DISCLOSURE = "OpenLarder earns a commission if you buy through these links.";
