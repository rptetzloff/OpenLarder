<script setup lang="ts">
import { signInHref } from "../auth";

// The address can change after this is drawn (a list's search box rewrites
// it), so the link is set again as it's reached: by pointer, by Tab, and
// at the click itself, which Enter makes too.
const fresh = (e: Event) => ((e.currentTarget as HTMLAnchorElement).href = signInHref());
</script>

<template>
  <!-- A full page load, not fetch: the broker's sign-in page is a redirect. -->
  <a :href="signInHref()" @pointerdown="fresh" @focus="fresh" @click="fresh"
    ><slot>Sign in</slot></a
  >
</template>
