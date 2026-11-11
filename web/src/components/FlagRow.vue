<script setup lang="ts">
import { computed, ref } from "vue";
import { applyTypo, type Flag, KIND_LABELS, resolveFlag, typo } from "../flags";

// One flag as a row of the flagged-recipes table, with Fixed and Dismiss.
// FlagItem is the same on a recipe's own page.
const props = defineProps<{ flag: Flag }>();
const emit = defineEmits<{ resolved: [flag: Flag] }>();

const f = computed(() => props.flag);
const dismissing = ref(false);
const reason = ref("");
const error = ref("");
const busy = ref(false);

// "Lemon Jucie → Lemon Juice": changed in one click (typos.py).
const suggested = computed(() => typo(f.value));

async function change() {
  busy.value = true;
  error.value = "";
  try {
    emit("resolved", await applyTypo(f.value.id));
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
    emit("resolved", await resolveFlag(f.value.id, resolution, reason.value || undefined));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <tr>
    <td>
      <a :href="`/recipes/${f.recipe.id}`" class="strong">{{ f.recipe.title }}</a>
      <div class="muted">
        <span class="cell-label">In </span>
        <a :href="`/sources/${f.recipe.source_id}`">{{ f.recipe.source_title }}</a>
      </div>
    </td>
    <td>
      {{ KIND_LABELS[f.kind] ?? f.kind }}
      <div v-if="f.detail" class="muted">{{ f.detail }}</div>
    </td>
    <td class="flag-actions">
      <template v-if="f.resolution">
        {{ f.resolution === "fixed" ? "Fixed" : "Dismissed" }}
        <span class="muted">{{ new Date(f.resolved_at!).toLocaleDateString() }}</span>
        <div v-if="f.note" class="muted">{{ f.note }}</div>
      </template>
      <template v-else-if="!dismissing">
        <button v-if="suggested" type="button" class="primary small" :disabled="busy" @click="change">
          Change to “{{ suggested.meant }}”
        </button>
        <button type="button" class="secondary small" :disabled="busy" @click="act('fixed')">Fixed</button>
        <button type="button" class="secondary small" :disabled="busy" @click="dismissing = true">
          Dismiss…
        </button>
      </template>
      <form v-else class="dismiss" @submit.prevent="act('dismissed')">
        <label :for="`why-${f.id}`">Why is the flag wrong?</label>
        <input :id="`why-${f.id}`" v-model="reason" maxlength="500" required />
        <div class="row-actions">
          <button type="submit" class="secondary small" :disabled="busy">Dismiss</button>
          <button type="button" class="link" @click="dismissing = false">Cancel</button>
        </div>
      </form>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </td>
  </tr>
</template>
