<script setup lang="ts">
import { onMounted, ref } from "vue";
import { acceptInvite, readInvite, rememberInvite, type Role, ROLE_NAMES } from "../groups";
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

// Signing in comes back to the front page; the app returns here from it.
function signIn() {
  rememberInvite(props.code);
  location.href = "/api/auth/login";
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
  <article>
    <h1>An invite</h1>
    <p v-if="problem" role="alert">{{ problem }}</p>
    <p v-else-if="!invite" class="status">Loading…</p>
    <template v-else>
      <p>
        You're invited to join <strong>{{ invite.group }}</strong> on OpenLarder:
        {{ ROLE_NAMES[invite.role].toLowerCase() }}.
      </p>
      <p class="status">
        Its members share private family collections with it. Joining shares nothing of yours;
        you choose that for each of your collections.
      </p>
      <p v-if="user === null">
        <button type="button" class="primary" @click="signIn">Sign in to join</button>
      </p>
      <p v-else-if="user">
        <button type="button" class="primary" :disabled="joining" @click="join">
          Join {{ invite.group }}
        </button>
      </p>
    </template>
  </article>
</template>
