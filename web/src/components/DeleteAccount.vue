<script setup lang="ts">
import { computed, ref } from "vue";
import type { Me } from "../me";

// Deleting your own account (account_deletion.py): typed out, then gone.
const props = defineProps<{ user: Me }>();

const open = ref(false);
const typed = ref("");
const busy = ref(false);
const error = ref("");
const expected = computed(() => props.user.display_name ?? "delete");

async function remove() {
  busy.value = true;
  error.value = "";
  try {
    const res = await fetch("/api/account/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: typed.value }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(typeof body.detail === "string" ? body.detail : "That didn't work. Try again.");
    }
    location.href = "/";
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    busy.value = false;
  }
}
</script>

<template>
  <section class="tool-panel delete-account" aria-labelledby="delete-title">
    <h2 id="delete-title">Delete your account</h2>
    <p v-if="user.role === 'owner'" class="muted">
      The owner's account can't be deleted here: make someone else the owner first.
    </p>
    <template v-else>
      <ul class="muted">
        <li>
          Goes now: your family collections and their history, your larder lists, shelf, saved recipes and ratings, what you've added
          that's still waiting for review, your suggested changes still open, your votes, your API
          keys, and you from your groups.
        </li>
        <li>
          A group you're the last admin of passes to its longest-standing member; one with nobody
          else in it is deleted.
        </li>
        <li>
          Stays, without your name: what's published in the catalog (you licensed it under the
          ODbL when you added it), and requests and reports you made.
        </li>
        <li>
          Your sign-in at Authgear stays: signing in again starts a new, empty account. To have it
          removed too, email <a href="mailto:privacy@openlarder.com">privacy@openlarder.com</a>.
        </li>
      </ul>
      <button v-if="!open" type="button" class="secondary" @click="open = true">
        Delete my account…
      </button>
      <form v-else @submit.prevent="remove">
        <label for="delete-confirm">Type “{{ expected }}” to delete your account. It can't be undone.</label>
        <input id="delete-confirm" v-model="typed" autocomplete="off" maxlength="64" />
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div class="actions">
          <button
            type="submit"
            class="primary"
            :disabled="busy || typed.trim().toLowerCase() !== expected.toLowerCase()"
          >
            {{ busy ? "Deleting…" : "Delete my account" }}
          </button>
          <button type="button" class="secondary" :disabled="busy" @click="open = false">
            Cancel
          </button>
        </div>
      </form>
    </template>
  </section>
</template>

<style scoped>
.delete-account ul {
  padding-left: 1.1rem;
  margin: 0 0 0.75rem;
  display: grid;
  gap: 0.35rem;
}
.delete-account label {
  display: block;
  margin-bottom: 0.3rem;
}
.delete-account input {
  font: inherit;
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  box-sizing: border-box;
  width: 100%;
  max-width: 20rem;
  margin-bottom: 0.5rem;
}
.actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}
</style>
