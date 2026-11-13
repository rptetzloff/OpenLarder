import { onBeforeUnmount, ref, type Ref } from "vue";

// Whether the window is a phone's width: 40rem and under, the breakpoint
// the stylesheets use. For what CSS can't do alone: putting a page's parts
// in another order in the document itself, so that Tab and a screen reader
// meet them in the order they're seen (CSS `order` moves only the picture).
export function useNarrow(): Ref<boolean> {
  const query = window.matchMedia("(max-width: 40rem)");
  const narrow = ref(query.matches);
  const update = () => (narrow.value = query.matches);
  query.addEventListener("change", update);
  onBeforeUnmount(() => query.removeEventListener("change", update));
  return narrow;
}
