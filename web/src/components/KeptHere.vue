<script setup lang="ts">
// The switch for keeping a copy of what is yours on this device, to read
// with no connection (offline.ts, public/sw.js). *Ray, 2026-11-17, asked
// on which devices a copy may be kept: "only where switched on".* Off to
// begin with, here and on every device, and it says what switching it on
// leaves behind, since the one who presses it on a shared computer is the
// one it would hurt.
import { onMounted, ref } from "vue";
import { canKeep, forgetHere, keepHere, keptHere } from "../offline";

const props = defineProps<{ userId: string }>();

// null until known; false too in a browser that can't keep one.
const kept = ref<boolean | null>(null);
const able = canKeep();
const busy = ref(false);
const error = ref("");

onMounted(async () => {
  kept.value = await keptHere().catch(() => false);
});

async function change(event: Event) {
  const wanted = (event.target as HTMLInputElement).checked;
  busy.value = true;
  error.value = "";
  try {
    if (wanted) await keepHere(props.userId);
    else await forgetHere();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    // What is so, whatever was asked for.
    kept.value = await keptHere().catch(() => false);
    busy.value = false;
  }
}
</script>

<template>
  <section class="tool-panel kept-here" aria-labelledby="kept-here-title">
    <h2 id="kept-here-title">This device</h2>
    <p v-if="!able" class="muted">
      This browser can't keep a copy of your kitchen to read with no connection.
    </p>
    <template v-else>
      <label class="check">
        <input
          id="keep-here"
          type="checkbox"
          :checked="kept === true"
          :disabled="busy || kept === null"
          aria-describedby="keep-here-help"
          @change="change"
        />
        Keep my kitchen on this device
      </label>
      <p id="keep-here-help" class="muted">
        Your larder, shelf, equipment and saved recipes, and each saved recipe's page, can then
        be read here with no connection.
        A copy of them stays on this device until you switch this off or sign out. Leave it off
        on a computer you share.
      </p>
      <p v-if="busy" class="status" role="status">
        {{ kept ? "Taking the copy off this device…" : "Keeping a copy…" }}
      </p>
      <p v-else-if="kept" class="status" role="status">A copy is kept on this device.</p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
    </template>
  </section>
</template>
