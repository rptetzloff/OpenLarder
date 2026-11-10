<script setup lang="ts">
import { onMounted, ref } from "vue";
import { type ApiKey, listKeys, makeKey, revokeKey } from "../apiKeys";

// Your API keys: make one (shown once), see when each was last used, revoke.
const keys = ref<ApiKey[] | null>(null);
const name = ref("");
const made = ref<string | null>(null);
const copied = ref(false);
const error = ref("");
const busy = ref(false);

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });

async function act(work: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await work();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

onMounted(() => act(async () => void (keys.value = await listKeys())));

const make = () =>
  act(async () => {
    const key = await makeKey(name.value);
    made.value = key.key;
    copied.value = false;
    name.value = "";
    keys.value = [...(keys.value ?? []), key];
  });

function revoke(key: ApiKey) {
  if (!confirm(`Revoke “${key.name}”? Anything using it stops working at once.`)) return;
  act(async () => {
    await revokeKey(key.id);
    keys.value = (keys.value ?? []).filter((k) => k.id !== key.id);
  });
}

async function copy() {
  try {
    await navigator.clipboard.writeText(made.value!);
    copied.value = true;
  } catch {
    // Selecting the text is the fallback; the field is there to select.
  }
}
</script>

<template>
  <section class="tool-panel api-keys" aria-labelledby="keys-title">
    <h2 id="keys-title">API keys</h2>
    <p class="muted">
      The <a href="/api/docs">public API</a> needs no key, at 60 requests a minute. A key raises it
      to 600. It reads what someone signed out sees, never your private collections.
    </p>
    <p v-if="keys === null && !error" class="status">Loading…</p>
    <ul v-else-if="keys?.length" class="key-list">
      <li v-for="k in keys" :key="k.id">
        <div>
          <strong>{{ k.name }}</strong> <code>{{ k.prefix }}…</code>
          <div class="muted">
            Made {{ day(k.created_at) }} ·
            {{ k.last_used_at ? `last used ${day(k.last_used_at)}` : "not used yet" }}
          </div>
        </div>
        <button type="button" class="secondary small" :disabled="busy" @click="revoke(k)">
          Revoke
        </button>
      </li>
    </ul>
    <div v-if="made" class="notice" role="status">
      <p>Here's the key. It won't be shown again; keep it somewhere safe.</p>
      <div class="inline-form">
        <label for="new-key" class="visually-hidden">The new key</label>
        <input id="new-key" :value="made" readonly @focus="($event.target as HTMLInputElement).select()" />
        <button type="button" class="primary" @click="copy">{{ copied ? "Copied" : "Copy" }}</button>
      </div>
    </div>
    <form class="recipe-form key-form" @submit.prevent="make">
      <label for="key-name">Make a key</label>
      <div class="row-actions">
        <input id="key-name" v-model="name" maxlength="60" placeholder="What it's for" required />
        <button type="submit" class="primary" :disabled="busy">Make it</button>
      </div>
    </form>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </section>
</template>
