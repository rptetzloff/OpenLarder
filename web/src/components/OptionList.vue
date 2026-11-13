<script setup lang="ts" generic="T extends { id: string }">
// The choices under a text box that's typed in to find something: an
// ingredient, a source, an author. Each is a real button, a row 44px tall,
// so Tab reaches them and Enter or Space takes one (the cleanup pass's
// rules); and the arrow keys move between the box and the choices, as
// people expect of a list under one. They were text buttons, which are
// for extras, not for what the box is there to choose.
import { onBeforeUnmount, onMounted, ref } from "vue";

const props = defineProps<{
  options: T[];
  // The id of the text box the choices are under.
  for: string;
  disabled?: boolean;
}>();
const emit = defineEmits<{ pick: [option: T] }>();

const list = ref<HTMLElement | null>(null);
const box = () => document.getElementById(props.for);
const choices = () => [...(list.value?.querySelectorAll<HTMLButtonElement>("button") ?? [])];

// Down from the box goes into the list. Listened for on the page, by the
// box's id, not on the box: the box is the parent's, not this list's, so
// nothing here says it exists when the list is mounted or is still the
// same element later.
function fromBox(event: KeyboardEvent) {
  if ((event.target as HTMLElement | null)?.id !== props.for) return;
  if (event.key === "ArrowDown" && choices().length) {
    event.preventDefault();
    choices()[0].focus();
  }
}
// Down and Up move through it; Up from the first, or Escape, goes back. So
// does typing: a letter, Backspace or Delete on a choice is meant for the
// box, which gets focus before the key acts, so it lands there. On a
// choice the keys did nothing, and the box seemed to have stopped taking
// them (chips.ts has what Ray asked, 2026-11-13). Space is left: it takes
// the choice, as Enter does.
function within(event: KeyboardEvent) {
  const all = choices();
  const at = all.indexOf(event.target as HTMLButtonElement);
  if (event.key === "ArrowDown") {
    event.preventDefault();
    all[Math.min(at + 1, all.length - 1)]?.focus();
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    if (at > 0) all[at - 1].focus();
    else box()?.focus();
  } else if (event.key === "Escape") {
    box()?.focus();
  } else if (
    event.key === "Backspace" ||
    event.key === "Delete" ||
    (event.key.length === 1 && event.key !== " " && !event.ctrlKey && !event.metaKey && !event.altKey)
  ) {
    box()?.focus();
  }
}
// Taking one puts focus back in the box, to type the next.
function pick(option: T) {
  emit("pick", option);
  box()?.focus();
}

onMounted(() => document.addEventListener("keydown", fromBox));
onBeforeUnmount(() => document.removeEventListener("keydown", fromBox));
</script>

<template>
  <ul v-if="options.length" ref="list" class="options" @keydown="within">
    <li v-for="o in options" :key="o.id">
      <button type="button" class="option" :disabled="disabled" @click="pick(o)">
        <slot :option="o" />
      </button>
    </li>
  </ul>
</template>

<style scoped>
.options {
  list-style: none;
  margin: 0.25rem 0 0;
  padding: 0.25rem;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--bg);
}
.options li {
  margin: 0;
}
.option {
  display: block;
  box-sizing: border-box;
  width: 100%;
  min-height: 2.75rem;
  padding: 0.5rem 0.625rem;
  border: none;
  border-radius: var(--radius-sm);
  background: none;
  color: var(--fg);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.option:hover,
.option:focus-visible {
  background: var(--chip);
}
.option:disabled {
  opacity: 0.45;
  cursor: default;
}
</style>
