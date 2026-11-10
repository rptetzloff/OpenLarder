<script setup lang="ts">
import { onMounted, ref } from "vue";
import { type Agreement, acceptAgreement, readAgreement } from "../review";

// The contributor agreement, to read and accept before adding to the
// catalog (agreement.py). Shows that it's accepted once it is.
const props = defineProps<{ agreed: boolean }>();
const emit = defineEmits<{ accepted: [] }>();

const agreement = ref<Agreement | null>(null);
const done = ref(props.agreed);
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
    <p v-if="done" class="status">
      You've accepted it, so what you add goes to the catalog under these terms.
    </p>
    <p v-else class="muted">Before you add to the catalog, please read and accept this.</p>
    <ol v-if="agreement" class="agreement-points">
      <li v-for="(point, i) in agreement.points" :key="i">{{ point }}</li>
    </ol>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <button v-if="!done" type="button" class="primary" :disabled="busy || !agreement" @click="accept">
      I accept the contributor agreement
    </button>
  </section>
</template>
