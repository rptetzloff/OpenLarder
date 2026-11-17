<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { chooseKitchenShop, kitchenShopNow, kitchenShops, loadKitchenShops } from "../kitchen";

// Which shop equipment's "Shop" links go to; shown only while a shop is on
// offer. GrocerChooser.vue over again (Ray, 2026-11-16: equipment is
// treated as ingredients are). The page says the commission beside it.
const props = defineProps<{ signedIn: boolean }>();
const error = ref("");
const now = computed(() => kitchenShopNow());

onMounted(loadKitchenShops);

async function change(event: Event) {
  error.value = "";
  try {
    await chooseKitchenShop((event.target as HTMLSelectElement).value, props.signedIn);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}
</script>

<template>
  <div v-if="now" class="grocer-chooser kitchen-shop-chooser">
    <label v-if="kitchenShops!.length > 1">
      Shop at
      <select :value="now.key" @change="change">
        <option v-for="k in kitchenShops" :key="k.key" :value="k.key">{{ k.label }}</option>
      </select>
    </label>
    <span v-else class="muted">Shop links go to {{ now.label }}.</span>
    <span v-if="error" class="error" role="alert">{{ error }}</span>
  </div>
</template>

<style scoped>
.grocer-chooser {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.25rem 1rem;
  font-size: var(--text-sm);
}
.grocer-chooser select {
  font: inherit;
  margin-left: 0.25rem;
  min-height: 2.75rem;
  padding: 0.2rem 0.4rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
}
</style>
