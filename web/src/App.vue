<script setup lang="ts">
import { onMounted, ref } from "vue";

// A placeholder until there is a catalog to show: proves the SPA reaches the
// API through whichever path it is served from, and that sign-in works.
const status = ref("checking…");
// undefined while asking, null when signed out.
const user = ref<{ display_name: string } | null | undefined>(undefined);
// The callback says only that sign-in failed, never why; the reason is in
// the server log, out of reach of whoever might be forging the request.
const signInFailed = new URLSearchParams(location.search).get("sign-in") === "failed";

onMounted(async () => {
  try {
    const res = await fetch("/readyz");
    const body = await res.json();
    status.value = res.ok ? `database ${body.database}, schema ${body.revision}` : body.database;
  } catch {
    status.value = "API unreachable";
  }
  try {
    const res = await fetch("/api/auth/me");
    user.value = res.ok ? await res.json() : null;
  } catch {
    user.value = null;
  }
});
</script>

<template>
  <header>
    <template v-if="user">
      <span>Signed in as {{ user.display_name }}</span>
      <!-- A form, not fetch: signing out ends at the broker, which ends the
           session there and sends the browser back here. -->
      <form method="post" action="/api/auth/logout">
        <button type="submit">Sign out</button>
      </form>
    </template>
    <!-- A full page load, not fetch: the broker's sign-in page is a redirect. -->
    <a v-else-if="user === null" href="/api/auth/login">Sign in</a>
  </header>
  <main>
    <h1>OpenLarder</h1>
    <p>A free, open index of the recipes in your cookbooks.</p>
    <p v-if="signInFailed" role="alert">Sign-in didn't work. Please try again.</p>
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
header {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 0.75rem;
  max-width: 40rem;
  margin: 0 auto;
  padding: 1rem 1rem 0;
  font-size: 0.875rem;
}
header form {
  margin: 0;
}
header a,
header button {
  color: var(--fg);
  text-decoration: underline;
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  cursor: pointer;
}
main {
  max-width: 40rem;
  margin: 0 auto;
  padding: 2rem 1rem 3rem;
}
.status {
  color: var(--muted);
  font-size: 0.875rem;
}
</style>
