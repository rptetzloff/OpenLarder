<script setup lang="ts">
import { onMounted, ref } from "vue";
import { signInHref } from "../auth";
import { acceptInvite, readInvite, type Role, ROLE_NAMES } from "../groups";
import type { Me } from "../me";

const props = defineProps<{ code: string; user: Me | null | undefined }>();
document.title = "An invite · OpenLarder";

const invite = ref<{ group: string; role: Role } | null>(null);
const problem = ref("");
const joining = ref(false);

onMounted(async () => {
  try {
    invite.value = await readInvite(props.code);
  } catch (e) {
    problem.value = e instanceof Error ? e.message : String(e);
  }
});

// Signing in comes back here, as it does to any page (auth.ts).
function signIn() {
  location.href = signInHref();
}

async function join() {
  joining.value = true;
  problem.value = "";
  try {
    const group = await acceptInvite(props.code);
    location.href = `/groups/${group.id}`;
  } catch (e) {
    problem.value = e instanceof Error ? e.message : String(e);
    joining.value = false;
  }
}
</script>

<template>
  <article class="wide">
    <div class="list-head">
      <h1>An invite</h1>
    </div>
    <p v-if="problem" role="alert">{{ problem }}</p>
    <p v-else-if="!invite" class="status">Loading…</p>
    <section v-else class="tool-panel invite-panel" aria-label="The invite">
      <p>
        You're invited to join <strong>{{ invite.group }}</strong> on OpenLarder:
        {{ ROLE_NAMES[invite.role].toLowerCase() }}.
      </p>
      <p class="muted">
        Its members share private family collections with it. Joining shares nothing of yours;
        you choose that for each of your collections.
      </p>
      <button v-if="user === null" type="button" class="primary" @click="signIn">
        Sign in to join
      </button>
      <button v-else-if="user" type="button" class="primary" :disabled="joining" @click="join">
        Join {{ invite.group }}
      </button>
    </section>
  </article>
</template>
