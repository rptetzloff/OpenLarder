<script setup lang="ts">
import { ref } from "vue";
import { type Change, cameThrough, label, madeBy, revertChange, shown } from "../history";

// Changes, newest first, each with what it added, changed or removed; for
// moderators, a button to undo one, after which the list is reloaded.
//
// A change of more than five rows is one line saying how many of what, with
// the rows behind "Show details" (Ray's round 4 list, B7, 2026-11-14: one
// import of 128 recipes listed every line it added, 5,240px on a phone).
const SHOWN_WHOLE = 5;
const opened = ref(new Set<string>());
function toggle(id: string) {
  const next = new Set(opened.value);
  if (!next.delete(id)) next.add(id);
  opened.value = next;
}
// "tag on the source" and "allergen a diet avoids" take their s on the first
// word; the rest on the last.
const plural = (what: string) => (/ (on|a) /.test(what) ? what.replace(" ", "s ") : `${what}s`);
// "added 128 recipes, 96 ingredient lines · changed 2 places", in the order
// the actions and the kinds first appear.
function summed(c: Change) {
  const by = new Map<string, Map<string, number>>();
  for (const e of c.entries) {
    const kinds = by.get(e.action) ?? new Map<string, number>();
    kinds.set(e.what, (kinds.get(e.what) ?? 0) + 1);
    by.set(e.action, kinds);
  }
  return [...by]
    .map(
      ([action, kinds]) =>
        `${action} ${[...kinds].map(([what, n]) => `${n.toLocaleString()} ${n === 1 ? what : plural(what)}`).join(", ")}`,
    )
    .join(" · ");
}
defineProps<{ changes: Change[]; linkSources?: boolean; canRevert?: boolean }>();
const emit = defineEmits<{ reverted: [] }>();
const errors = ref<Record<string, string>>({});
const busy = ref(false);

async function undo(c: Change) {
  if (!confirm("Undo this change? It's put back as it was before, as a new change in the history.")) return;
  busy.value = true;
  errors.value = {};
  try {
    await revertChange(c.id);
    emit("reverted");
  } catch (e) {
    errors.value = { [c.id]: e instanceof Error ? e.message : String(e) };
  } finally {
    busy.value = false;
  }
}
const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
</script>

<template>
  <ol class="change-list">
    <li v-for="c in changes" :key="c.id">
      <p class="change-head">
        <strong>{{ madeBy(c) }}</strong>
        <span class="muted">
          · <time :datetime="c.at">{{ when(c.at) }}</time>
          <template v-if="cameThrough(c.via)"> · through {{ cameThrough(c.via) }}</template>
          <template v-if="c.entries.length > SHOWN_WHOLE"> · {{ summed(c) }}</template>
          <template v-if="linkSources && c.source_id">
            · <a :href="`/sources/${c.source_id}`">the source</a>
          </template>
        </span>
        <button
          v-if="canRevert && !c.withheld"
          type="button"
          class="secondary small change-undo"
          :disabled="busy"
          @click="undo(c)"
        >
          Undo
        </button>
      </p>
      <p v-if="errors[c.id]" class="error" role="alert">{{ errors[c.id] }}</p>
      <button
        v-if="c.entries.length > SHOWN_WHOLE"
        type="button"
        class="link change-more"
        :aria-expanded="opened.has(c.id)"
        :aria-controls="`change-${c.id}`"
        @click="toggle(c.id)"
      >
        {{ opened.has(c.id) ? "Hide details" : "Show details" }}
      </button>
      <ul
        v-show="c.entries.length <= SHOWN_WHOLE || opened.has(c.id)"
        :id="`change-${c.id}`"
        class="change-entries"
      >
        <li v-for="(e, i) in c.entries" :key="i">
          <span class="change-action" :class="e.action">{{ e.action }}</span>{{ " " }}
          {{ e.what }}{{ e.name ? ` ${shown(e.name)}` : "" }}
          <ul v-if="e.action === 'changed' && e.fields.length" class="change-fields">
            <li v-for="f in e.fields" :key="f.field">
              {{ label(f.field) }}: {{ shown(f.before) }} → {{ shown(f.after) }}
            </li>
          </ul>
        </li>
      </ul>
    </li>
  </ol>
</template>
