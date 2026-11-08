<script setup lang="ts">
import { ref } from "vue";
import { removeSwap, type Swap, type Thing } from "../substitutions";

// Swaps as a list: "Instead of Butter, Coconut Oil · Dairy-Free · Book, p. 12".
const props = defineProps<{ swaps: Swap[]; canEdit: boolean }>();
const emit = defineEmits<{ removed: [id: string] }>();
const error = ref("");

function href(t: Thing) {
  return t.kind === "ingredient" ? `/ingredients/${t.id}` : `/recipes/${t.id}`;
}

async function remove(s: Swap) {
  if (!confirm(`Remove the swap of ${s.use.name} for ${s.instead_of.name}?`)) return;
  error.value = "";
  try {
    await removeSwap(s.id);
    emit("removed", s.id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}
</script>

<template>
  <ul class="swap-list">
    <li v-for="s in props.swaps" :key="s.id">
      Instead of <a :href="href(s.instead_of)">{{ s.instead_of.name }}</a>,
      <a :href="href(s.use)">{{ s.use.name }}</a>
      <span class="page-ref">
        <template v-if="s.diet">{{ s.diet.name }}</template>
        <template v-if="s.diet && s.source"> · </template>
        <template v-if="s.source">
          <a :href="`/books/${s.source.book_id}`">{{ s.source.book_title }}</a
          ><template v-if="s.source.page">, p. {{ s.source.page }}</template>
        </template>
      </span>
      <span v-if="s.note" class="swap-note">{{ s.note }}</span>
      <button
        v-if="canEdit"
        type="button"
        class="link remove-alias"
        :aria-label="`Remove the swap of ${s.use.name} for ${s.instead_of.name}`"
        @click="remove(s)"
      >
        ×
      </button>
    </li>
  </ul>
  <p v-if="error" class="error" role="alert">{{ error }}</p>
</template>
