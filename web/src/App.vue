<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import NameForm from "./components/NameForm.vue";
import type { Me } from "./me";
import AccountPage from "./pages/AccountPage.vue";
import PrivacyPage from "./pages/PrivacyPage.vue";
import TermsPage from "./pages/TermsPage.vue";

// The server returns this app for any path it has no file for, so the page
// is chosen from the address. Two fixed pages don't need a router library;
// the catalog's pages will bring one.
const pages: Record<string, unknown> = { "/privacy": PrivacyPage, "/terms": TermsPage };
const path = location.pathname.replace(/\/+$/, "");
const page = pages[path];
const onAccount = path === "/account";

// A placeholder until there is a catalog to show: proves the SPA reaches the
// API through whichever path it is served from, and that sign-in works.
const status = ref("checking…");
// undefined while asking, null when signed out.
const user = ref<Me | null | undefined>(undefined);
// Someone signed in who hasn't chosen a name yet is asked for one before
// anything else, except the privacy and terms pages, which stay readable.
const needsName = computed(() => !!user.value && !user.value.display_name && !page);
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
      <a href="/account">{{ user.display_name ?? "Choose a name" }}</a>
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
    <component :is="page" v-if="page" />
    <section v-else-if="needsName && user">
      <h1>What should we call you?</h1>
      <p>Pick the name OpenLarder shows for you. You can change it later on your account page.</p>
      <NameForm
        :initial="user.suggested_name ?? ''"
        submit-label="Continue"
        @saved="(me) => (user = me)"
      />
    </section>
    <AccountPage v-else-if="onAccount" :user="user" @saved="(me) => (user = me)" />
    <template v-else>
      <h1>OpenLarder</h1>
      <p>A free, open index of the recipes in your cookbooks.</p>
      <p v-if="signInFailed" role="alert">Sign-in didn't work. Please try again.</p>
      <p class="status">{{ status }}</p>
    </template>
  </main>
  <footer>
    <a href="/">OpenLarder</a>
    <a href="/privacy">Privacy</a>
    <a href="/terms">Terms</a>
  </footer>
</template>

<style>
:root {
  --bg: #fbfaf7;
  --fg: #1f1e1c;
  --muted: #5f5e5a;
  --accent: #8a5a1c;
  --accent-hover: #734a15;
  --on-accent: #ffffff;
  --border: #8a877f;
  --error: #b3261e;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1a1918;
    --fg: #ecebe6;
    --muted: #a8a59c;
    /* The logo's amber, with dark text: white on it is 2.2:1. */
    --accent: #e0a24a;
    --accent-hover: #ebb368;
    --on-accent: #1f1e1c;
    --border: #77746c;
    --error: #f2a8a2;
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
header button,
footer a {
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
.status,
.updated {
  color: var(--muted);
  font-size: 0.875rem;
}
main a {
  color: var(--fg);
}
main li {
  margin-bottom: 0.5rem;
}
main h2 {
  margin-top: 2rem;
  font-size: 1.125rem;
}
.name-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 24rem;
}
.name-form label {
  font-weight: 600;
}
.name-form input {
  font: inherit;
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.name-form .help {
  margin: 0;
  color: var(--muted);
  font-size: 0.875rem;
}
.name-form .error {
  margin: 0;
  color: var(--error);
}
button.primary {
  align-self: flex-start;
  font: inherit;
  font-weight: 600;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 8px;
  background: var(--accent);
  color: var(--on-accent);
  cursor: pointer;
}
button.primary:hover {
  background: var(--accent-hover);
}
button.primary:disabled {
  opacity: 0.6;
  cursor: default;
}
footer {
  display: flex;
  gap: 1rem;
  max-width: 40rem;
  margin: 0 auto;
  padding: 0 1rem 2rem;
  font-size: 0.875rem;
}
</style>
