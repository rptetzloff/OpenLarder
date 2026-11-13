<script setup lang="ts">
import { watchEffect } from "vue";
import NameForm from "../components/NameForm.vue";
import type { Me } from "../me";

// Where a new account chooses its name (routers/auth.py sends it here).
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Welcome · OpenLarder";

// Nothing here for anyone signed out, or named already. The server sends
// them to the front page before this is drawn (main.py); this is for an
// address it doesn't match, and a development server.
watchEffect(() => {
  if (props.user === null || props.user?.display_name) location.replace("/");
});

// On to the page sign-in began on, which the server kept.
const carryOn = () => (location.href = "/api/auth/continue");
</script>

<template>
  <article v-if="user && !user.display_name" class="welcome">
    <h1>Welcome to OpenLarder</h1>
    <p>Pick the name OpenLarder shows for you. You can change it later on your account page.</p>
    <NameForm :initial="user.suggested_name ?? ''" submit-label="Continue" @saved="carryOn">
      <div class="what-for">
        <p>With an account you can:</p>
        <ul>
          <li>Keep a shelf of the books you own.</li>
          <li>Keep a larder of what you have.</li>
          <li>Save and rate recipes.</li>
        </ul>
      </div>
    </NameForm>
  </article>
</template>

<style scoped>
.what-for {
  margin: 0.5rem 0;
}
.what-for p {
  margin: 0;
}
.what-for ul {
  margin: 0.25rem 0 0;
  padding-left: 1.25rem;
}
</style>
