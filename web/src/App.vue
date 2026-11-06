<script setup lang="ts">
import { onMounted, ref } from "vue";

// A placeholder until there is a catalog to show: proves the SPA reaches the
// API through whichever path it is served from.
const status = ref("checking…");

onMounted(async () => {
  try {
    const res = await fetch("/readyz");
    const body = await res.json();
    status.value = res.ok ? `database ${body.database}, schema ${body.revision}` : body.database;
  } catch {
    status.value = "API unreachable";
  }
});
</script>

<template>
  <main>
    <h1>OpenLarder</h1>
    <p>A free, open index of the recipes in your cookbooks.</p>
    <p class="status">{{ status }}</p>
  </main>
</template>

<style>
:root {
  --bg: #fbfaf7;
  --fg: #1f1e1c;
  --muted: #5f5e5a;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1a1918;
    --fg: #ecebe6;
    --muted: #a8a59c;
  }
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: system-ui, sans-serif;
}
main {
  max-width: 40rem;
  margin: 0 auto;
  padding: 3rem 1rem;
}
.status {
  color: var(--muted);
  font-size: 0.875rem;
}
</style>
