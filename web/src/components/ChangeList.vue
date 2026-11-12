<script setup lang="ts">
import { ref } from "vue";
import { type Change, cameThrough, label, madeBy, revertChange, shown } from "../history";

// Changes, newest first, each with what it added, changed or removed; for
// moderators, a button to undo one, after which the list is reloaded.
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
      <ul class="change-entries">
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
