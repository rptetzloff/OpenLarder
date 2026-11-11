<script setup lang="ts">
import { computed, ref } from "vue";
import { type BuyLink, shopName } from "../buying";
import { arrange, saveShopPrefs, shopPrefs } from "../shops";

// Choosing the buy-link shops: their order, and which to hide, one always
// left. Each change applies at once, on every book and recipe.
const props = defineProps<{ links: BuyLink[]; signedIn: boolean }>();

const error = ref("");
const labels = computed(() => new Map(props.links.map((l) => [l.retailer, shopName(l)])));
const hidden = computed(() => new Set(shopPrefs.value?.hidden ?? []));
// Every shop offered here, hidden ones too, in the order chosen.
const order = computed(() =>
  arrange(props.links, { order: shopPrefs.value?.order ?? [], hidden: [] }).map((l) => l.retailer),
);
const showing = computed(() => order.value.filter((k) => !hidden.value.has(k)).length);

async function save(nextOrder: string[], nextHidden: string[]) {
  error.value = "";
  // Shops not offered here keep their place after these.
  const elsewhere = (shopPrefs.value?.order ?? []).filter((k) => !nextOrder.includes(k));
  try {
    await saveShopPrefs({ order: [...nextOrder, ...elsewhere], hidden: nextHidden }, props.signedIn);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

function toggle(key: string) {
  const now = [...hidden.value];
  save(order.value, hidden.value.has(key) ? now.filter((k) => k !== key) : [...now, key]);
}

function move(index: number, by: -1 | 1) {
  const next = [...order.value];
  [next[index], next[index + by]] = [next[index + by], next[index]];
  save(next, [...hidden.value]);
}
</script>

<template>
  <details class="shop-chooser">
    <summary>Choose your shops</summary>
    <p class="help">
      Put the shops you use first, and hide the rest; one always shows. It applies on every book
      and recipe{{ signedIn ? ", kept with your account" : " in this browser" }}.
    </p>
    <ol class="shop-list">
      <li v-for="(key, i) in order" :key="key">
        <label>
          <input
            type="checkbox"
            :checked="!hidden.has(key)"
            :disabled="!hidden.has(key) && showing === 1"
            @change="toggle(key)"
          />
          {{ labels.get(key) }}
        </label>
        <span class="shop-moves">
          <button
            type="button"
            class="secondary small"
            :disabled="i === 0"
            :aria-label="`Move ${labels.get(key)} up`"
            @click="move(i, -1)"
          >
            ↑
          </button>
          <button
            type="button"
            class="secondary small"
            :disabled="i === order.length - 1"
            :aria-label="`Move ${labels.get(key)} down`"
            @click="move(i, 1)"
          >
            ↓
          </button>
        </span>
      </li>
    </ol>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </details>
</template>
