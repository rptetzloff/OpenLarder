<script setup lang="ts">
import { ref } from "vue";
import { type Change, type Kind, historyOf } from "../history";
import ChangeList from "./ChangeList.vue";

// A record's edit history, folded away until opened, and loaded then.
// startOpen: asked for already, so open and loading from the start.
const props = defineProps<{ kind: Kind; id: string; canRevert?: boolean; startOpen?: boolean }>();
const changes = ref<Change[] | null>(null);
const error = ref("");

async function load() {
  try {
    changes.value = await historyOf(props.kind, props.id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

function opened(event: Event) {
  if ((event.target as HTMLDetailsElement).open && !changes.value) load();
}

if (props.startOpen) load();

// An undo changes the record itself: the whole page reloads to show it.
const reverted = () => location.reload();
</script>

<template>
  <details class="history-panel" :open="startOpen" @toggle="opened">
    <summary>History</summary>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-else-if="!changes" class="status">Loading…</p>
    <ChangeList
      v-else-if="changes.length"
      :changes="changes"
      :can-revert="canRevert"
      @reverted="reverted"
    />
    <p v-else class="status">No changes recorded yet. History began on November 10, 2026.</p>
  </details>
</template>
