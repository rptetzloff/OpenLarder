// A box that holds what's been chosen as chips, with a text box after them
// to find the next (the Search page's ingredients and sources, the larder
// picker's things).

// Backspace or Delete in the empty text box takes the last chip away, as
// people expect of chips in a box. *Ray, 2026-11-13: "we also need to be
// able to back space and delete in the search fields... it doesn't work
// today".* Typed text was already edited by both keys in every search box
// (tried with real key presses); what they didn't do was this, and work
// from the list of choices (OptionList.vue). That those are what he met is
// Claude's reading. Before, a chip went only by its ×.
//
// Not while the key is held: holding Backspace to clear what's typed
// shouldn't go on to clear what's chosen. And only when the box is empty,
// so with something typed the keys edit it as they always did.
export function dropLastOn<T>(event: KeyboardEvent, chosen: T[], drop: (last: T) => void): void {
  if (event.key !== "Backspace" && event.key !== "Delete") return;
  if (event.repeat || !chosen.length) return;
  if ((event.target as HTMLInputElement).value !== "") return;
  event.preventDefault();
  drop(chosen[chosen.length - 1]);
}
