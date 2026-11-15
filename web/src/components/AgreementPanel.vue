<script setup lang="ts">
import { onMounted, ref } from "vue";
import { type Agreement, acceptAgreement, readAgreement } from "../review";

// The contributor agreement, to read and accept before adding to the
// catalog (agreement.py). Once it's accepted it says when, and its words
// are folded under "Read the agreement" (Ray's round 5 list, item 8,
// 2026-11-15: printed in full it made Your account 2,734px on a phone).
const props = defineProps<{ agreed: boolean; agreedAt?: string | null }>();
const emit = defineEmits<{ accepted: [] }>();

const agreement = ref<Agreement | null>(null);
const done = ref(props.agreed);
// When: the server's date, or now for one accepted on this page.
const at = ref(props.agreedAt ?? null);
const when = (iso: string) =>
  new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
const error = ref("");
const busy = ref(false);

onMounted(async () => {
  try {
    agreement.value = await readAgreement();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
});

async function accept() {
  if (!agreement.value) return;
  busy.value = true;
  error.value = "";
  try {
    await acceptAgreement(agreement.value.version);
    done.value = true;
    at.value = new Date().toISOString();
    emit("accepted");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="tool-panel agreement-panel" aria-labelledby="agreement-title">
    <h2 id="agreement-title">Contributor agreement</h2>
    <template v-if="done">
      <p class="status">
        {{ at ? `Accepted on ${when(at)}.` : "You've accepted it." }}
        What you add goes to the catalog under these terms.
      </p>
      <details v-if="agreement" class="how">
        <summary>Read the agreement</summary>
        <ol class="agreement-points">
          <li v-for="(point, i) in agreement.points" :key="i">{{ point }}</li>
        </ol>
      </details>
    </template>
    <template v-else>
      <p class="muted">Before you add to the catalog, please read and accept this.</p>
      <ol v-if="agreement" class="agreement-points">
        <li v-for="(point, i) in agreement.points" :key="i">{{ point }}</li>
      </ol>
    </template>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <button v-if="!done" type="button" class="primary" :disabled="busy || !agreement" @click="accept">
      I accept the contributor agreement
    </button>
  </section>
</template>
