<script setup lang="ts">
import { ref } from "vue";
import { type Kind, REASONS, type Reason, sendReport } from "../reports";

// "Report a problem" on a public record, for anyone (routers/reports.py).
// *Ray, 2026-11-10.*
const props = defineProps<{ kind: Kind; id: string }>();

const open = ref(false);
const reason = ref<Reason>("wrong");
const note = ref("");
// Never shown to people; a bot fills it in.
const website = ref("");
const sent = ref(false);
const error = ref("");
const busy = ref(false);

async function submit() {
  busy.value = true;
  error.value = "";
  try {
    await sendReport({
      kind: props.kind,
      id: props.id,
      reason: reason.value,
      note: note.value,
      website: website.value,
    });
    sent.value = true;
    open.value = false;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="report-problem">
    <p v-if="sent" class="status" role="status">Thanks: a moderator will look at it.</p>
    <button
      v-else-if="!open"
      type="button"
      class="link"
      :aria-expanded="open"
      @click="open = true"
    >
      Report a problem
    </button>
    <form v-if="open" class="recipe-form report-form" @submit.prevent="submit">
      <fieldset>
        <legend>What's the problem?</legend>
        <label v-for="r in REASONS" :key="r.reason" class="check">
          <input v-model="reason" type="radio" name="report-reason" :value="r.reason" />
          {{ r.label }}
        </label>
      </fieldset>
      <label :for="`report-note-${id}`">Anything to add? (optional)</label>
      <textarea
        :id="`report-note-${id}`"
        v-model="note"
        rows="3"
        maxlength="1000"
        placeholder="It's on page 14 in my copy"
      ></textarea>
      <div class="visually-hidden" aria-hidden="true">
        <label :for="`report-website-${id}`">Leave this empty</label>
        <input :id="`report-website-${id}`" v-model="website" tabindex="-1" autocomplete="off" />
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="row-actions">
        <button type="submit" class="primary" :disabled="busy">Send the report</button>
        <button type="button" class="secondary" :disabled="busy" @click="open = false">
          Cancel
        </button>
      </div>
    </form>
  </div>
</template>
