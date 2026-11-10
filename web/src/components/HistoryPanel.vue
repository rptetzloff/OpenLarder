<script setup lang="ts">
import { ref } from "vue";
import { type Change, type Kind, historyOf } from "../history";
import ChangeList from "./ChangeList.vue";

// A record's edit history, folded away until opened, and loaded then.
const props = defineProps<{ kind: Kind; id: string }>();
const changes = ref<Change[] | null>(null);
const error = ref("");

async function opened(event: Event) {
  if (!(event.target as HTMLDetailsElement).open || changes.value) return;
  try {
    changes.value = await historyOf(props.kind, props.id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}
</script>

<template>
  <details class="history-panel" @toggle="opened">
    <summary>History</summary>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-else-if="!changes" class="status">Loading…</p>
    <ChangeList v-else-if="changes.length" :changes="changes" />
    <p v-else class="status">No changes recorded yet. History began on 10 November 2026.</p>
  </details>
</template>
