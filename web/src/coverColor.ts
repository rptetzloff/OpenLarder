// The colour a source's drawn cover has, picked from its title so a shelf of
// them isn't one colour, and the same wherever the source is shown: on its
// drawn cover (CoverBlank.vue) and in a result's thumbnail (CoverThumb.vue).

// Each dark enough for the cream and gold text (4.5:1 or better).
const COLOURS = ["#2e4a3b", "#7a3418", "#2b3f57", "#5a3350", "#3d4a1e"];

export function coverColor(title: string): string {
  let h = 0;
  for (const c of title) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return COLOURS[h % COLOURS.length];
}
