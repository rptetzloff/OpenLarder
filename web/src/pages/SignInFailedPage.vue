<script setup lang="ts">
import SignInLink from "../components/SignInLink.vue";

// Where a sign-in that didn't work lands (routers/auth.py). It says only
// that it failed, never why: the reason is in the server log, out of reach
// of whoever might be forging the request.
document.title = "Sign-in didn't work · OpenLarder";
</script>

<template>
  <article>
    <h1>Sign-in didn't work</h1>
    <p>Nothing was changed. Please try again.</p>
    <p class="choices">
      <SignInLink class="primary">Try again</SignInLink>
      <a href="/">Back to the home page</a>
    </p>
  </article>
</template>

<style scoped>
.choices {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1.25rem;
}
/* As tall to tap as the button beside it. */
.choices a:not(.primary) {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
}
</style>
