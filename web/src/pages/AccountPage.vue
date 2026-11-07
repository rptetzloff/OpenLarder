<script setup lang="ts">
import NameForm from "../components/NameForm.vue";
import type { Me } from "../me";

defineProps<{ user: Me | null | undefined }>();
const emit = defineEmits<{ saved: [me: Me] }>();
document.title = "Your account · OpenLarder";
</script>

<template>
  <article>
    <h1>Your account</h1>
    <p v-if="user === null">
      <a href="/api/auth/login">Sign in</a> to see your account.
    </p>
    <template v-else-if="user">
      <NameForm
        :initial="user.display_name ?? user.suggested_name ?? ''"
        submit-label="Save"
        @saved="(me) => emit('saved', me)"
      />
      <h2>Flagged recipes</h2>
      <p>
        <a href="/account/flags">My flagged recipes</a>: anything about a recipe you added that
        needs a look.
      </p>
      <h2>Signing in</h2>
      <p>
        Your email address, Google or GitHub link and passkeys are kept by Authgear, which
        handles sign-in for OpenLarder.
      </p>
      <p v-if="user.account_url">
        <a :href="user.account_url">Manage sign-in methods and passkeys</a>
      </p>
    </template>
  </article>
</template>
