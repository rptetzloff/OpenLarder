<script setup lang="ts">
import { ref } from "vue";
import { checkOpenLibrary, type Difference, takeFromOpenLibrary } from "../books";

// What differs between the book here and Open Library now; tick what to
// take. Nothing is ticked to start with: what's here may be a fix made here.
const props = defineProps<{ bookId: string }>();
const emit = defineEmits<{ taken: [] }>();

const differences = ref<Difference[] | null>(null);
const ticked = ref<string[]>([]);
const error = ref("");
const busy = ref(false);
const done = ref("");

async function check() {
  error.value = "";
  done.value = "";
  busy.value = true;
  try {
    differences.value = (await checkOpenLibrary(props.bookId)).differences;
    ticked.value = [];
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function take() {
  error.value = "";
  busy.value = true;
  try {
    const result = await takeFromOpenLibrary(props.bookId, ticked.value);
    differences.value = result.differences;
    ticked.value = [];
    done.value = `Took ${result.taken} ${result.taken === 1 ? "change" : "changes"}.`;
    emit("taken");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <section class="ol-link">
    <button type="button" class="secondary small" :disabled="busy" @click="check">
      {{ busy && differences === null ? "Checking Open Library…" : "Check Open Library" }}
    </button>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <template v-if="differences">
      <p v-if="done" class="status">{{ done }}</p>
      <p v-if="!differences.length" class="status">Open Library says the same as this page.</p>
      <form v-else class="ol-preview" @submit.prevent="take">
        <p class="status">
          Open Library differs on these. Tick the ones to take; the rest stay as they are here.
        </p>
        <ul class="ol-differences">
          <li v-for="d in differences" :key="d.key">
            <label class="check">
              <input v-model="ticked" type="checkbox" :value="d.key" />
              <strong>{{ d.label }}</strong>
            </label>
            <span v-if="d.cover" class="ol-covers">
              <img v-if="d.ours" :src="d.ours" alt="The cover here" />
              <span v-else class="status">no cover</span>
              →
              <img v-if="d.theirs" :src="d.theirs" alt="Open Library's cover" />
            </span>
            <span v-else class="ol-values">
              <span class="ours">{{ d.ours ?? "(blank)" }}</span>
              →
              <span class="theirs">{{ d.theirs ?? "(blank)" }}</span>
            </span>
          </li>
        </ul>
        <button type="submit" class="primary" :disabled="busy || !ticked.length">
          Take {{ ticked.length || "" }} from Open Library
        </button>
      </form>
    </template>
  </section>
</template>
