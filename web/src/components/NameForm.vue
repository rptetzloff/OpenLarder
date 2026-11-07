<script setup lang="ts">
import { ref } from "vue";
import { type Me, saveDisplayName } from "../me";

const props = defineProps<{ initial: string; submitLabel: string }>();
const emit = defineEmits<{ saved: [me: Me] }>();

const name = ref(props.initial);
const error = ref("");
const saving = ref(false);

async function submit() {
  saving.value = true;
  error.value = "";
  try {
    emit("saved", await saveDisplayName(name.value));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <form class="name-form" @submit.prevent="submit">
    <label for="display-name">Display name</label>
    <input
      id="display-name"
      v-model="name"
      autocomplete="nickname"
      maxlength="32"
      required
      :aria-invalid="error ? 'true' : undefined"
      aria-describedby="display-name-help display-name-error"
    />
    <p id="display-name-help" class="help">
      Shown beside anything you add to the catalog. 2 to 32 letters or numbers; it has to be
      one nobody else has.
    </p>
    <p v-if="error" id="display-name-error" class="error" role="alert">{{ error }}</p>
    <button type="submit" class="primary" :disabled="saving">{{ submitLabel }}</button>
  </form>
</template>
