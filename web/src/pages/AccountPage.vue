<script setup lang="ts">
import { ref, watch } from "vue";
import AgreementPanel from "../components/AgreementPanel.vue";
import ApiKeys from "../components/ApiKeys.vue";
import ContributionsPanel from "../components/ContributionsPanel.vue";
import NameForm from "../components/NameForm.vue";
import { fetchFlags } from "../flags";
import { listGroups } from "../groups";
import type { Me } from "../me";

const props = defineProps<{ user: Me | null | undefined }>();
const emit = defineEmits<{ saved: [me: Me] }>();
document.title = "Your account · OpenLarder";

// What's waiting, on each card; null until known, or if it couldn't be.
const openFlags = ref<number | null>(null);
const groups = ref<number | null>(null);

async function loadCounts() {
  const [flags, mine] = await Promise.allSettled([
    fetchFlags({ scope: "mine", state: "open" }),
    listGroups(),
  ]);
  if (flags.status === "fulfilled")
    openFlags.value = Object.values(flags.value.open_by_kind).reduce((a, b) => a + b, 0);
  if (mine.status === "fulfilled") groups.value = mine.value.length;
}
// Who's signed in arrives after the page mounts.
watch(
  () => !!props.user,
  (yes) => {
    if (yes) loadCounts();
  },
  { immediate: true },
);
// Accepting the agreement changes what the whole app lets you do.
async function accepted() {
  const res = await fetch("/api/auth/me");
  if (res.ok) emit("saved", await res.json());
}
const n = (v: number | null, one: string, many: string) =>
  v === null ? "" : `${v.toLocaleString()} ${v === 1 ? one : many}`;
</script>

<template>
  <article class="wide">
    <div class="list-head">
      <h1>Your account</h1>
      <p v-if="user?.display_name" class="muted">Signed in as {{ user.display_name }}.</p>
    </div>
    <p v-if="user === null" class="status">
      <a href="/api/auth/login">Sign in</a> to see your account.
    </p>
    <template v-else-if="user">
      <ul class="link-cards">
        <li>
          <a href="/account/flags">
            <h2>My flagged recipes</h2>
            <p class="count">{{ n(openFlags, "open", "open") }}</p>
            <p>Anything about a recipe you added that needs a look.</p>
          </a>
        </li>
        <li>
          <a href="/groups">
            <h2>Groups</h2>
            <p class="count">{{ n(groups, "group", "groups") }}</p>
            <p>Family and friends you share your private collections with.</p>
          </a>
        </li>
      </ul>

      <div class="tool-panels account-panels">
        <section class="tool-panel" aria-labelledby="name-title">
          <h2 id="name-title">Profile</h2>
          <NameForm
            :initial="user.display_name ?? user.suggested_name ?? ''"
            submit-label="Save"
            @saved="(me) => emit('saved', me)"
          />
        </section>
        <section class="tool-panel" aria-labelledby="sign-in-title">
          <h2 id="sign-in-title">Signing in</h2>
          <p class="muted">
            Your email address, Google or GitHub link and passkeys are kept by Authgear, which
            handles sign-in for OpenLarder.
          </p>
          <p v-if="user.account_url">
            <a :href="user.account_url">Manage sign-in methods and passkeys</a>
          </p>
        </section>
      </div>
      <div v-if="user.may_claim" class="tool-panels account-panels">
        <AgreementPanel :agreed="user.agreed" @accepted="accepted" />
        <ContributionsPanel />
      </div>
      <ApiKeys />
    </template>
  </article>
</template>
