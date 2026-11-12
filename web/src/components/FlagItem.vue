<script setup lang="ts">
import { ref } from "vue";
import { applyTypo, type Flag, KIND_LABELS, resolveFlag, typo } from "../flags";

// One flag, with Fixed and Dismiss for someone who may deal with it.
const props = defineProps<{ flag: Flag; showRecipe: boolean }>();
const emit = defineEmits<{ resolved: [flag: Flag] }>();

const dismissing = ref(false);
const reason = ref("");
const error = ref("");
const busy = ref(false);

// "Lemon Jucie → Lemon Juice": changed in one click (typos.py).
const suggested = typo(props.flag);

async function change() {
  busy.value = true;
  error.value = "";
  try {
    emit("resolved", await applyTypo(props.flag.id));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function act(resolution: "fixed" | "dismissed") {
  busy.value = true;
  error.value = "";
  try {
    emit("resolved", await resolveFlag(props.flag.id, resolution, reason.value || undefined));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <li class="flag">
    <p class="flag-what">
      <strong>{{ KIND_LABELS[flag.kind] ?? flag.kind }}</strong>
      <span v-if="flag.detail">: {{ flag.detail }}</span>
    </p>
    <p v-if="showRecipe" class="byline">
      <a :href="`/recipes/${flag.recipe.id}`">{{ flag.recipe.title }}</a>
      in <a :href="`/sources/${flag.recipe.source_id}`">{{ flag.recipe.source_title }}</a>
    </p>
    <p v-if="flag.resolution" class="status">
      {{ flag.resolution === "fixed" ? "Fixed" : "Dismissed" }}
      {{ new Date(flag.resolved_at!).toLocaleDateString() }}<span v-if="flag.note">: {{ flag.note }}</span>
    </p>
    <template v-else>
      <div v-if="!dismissing" class="admin-actions">
        <button v-if="suggested" type="button" class="secondary small" :disabled="busy" @click="change">
          Change to “{{ suggested.meant }}”
        </button>
        <button type="button" class="secondary small" :disabled="busy" @click="act('fixed')">Fixed</button>
        <button type="button" class="secondary small" :disabled="busy" @click="dismissing = true">Dismiss…</button>
      </div>
      <form v-else class="dismiss" @submit.prevent="act('dismissed')">
        <label :for="`why-${flag.id}`">Why is the flag wrong?</label>
        <input :id="`why-${flag.id}`" v-model="reason" maxlength="500" required />
        <div class="admin-actions">
          <button type="submit" class="secondary small" :disabled="busy">Dismiss</button>
          <button type="button" class="link" @click="dismissing = false">Cancel</button>
        </div>
      </form>
    </template>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </li>
</template>
