<script setup lang="ts">
import { onMounted, ref } from "vue";
import { type GroupSummary, listGroups, makeGroup, ROLE_NAMES } from "../groups";
import type { Me } from "../me";

defineProps<{ user: Me | null | undefined }>();
document.title = "Groups · OpenLarder";

const groups = ref<GroupSummary[] | null>(null);
const failed = ref(false);
const name = ref("");
const error = ref("");

onMounted(async () => {
  try {
    groups.value = await listGroups();
  } catch {
    failed.value = true;
  }
});

async function make() {
  error.value = "";
  try {
    const made = await makeGroup(name.value);
    location.href = `/groups/${made.id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}
</script>

<template>
  <article>
    <h1>Groups</h1>
    <p class="status">
      A group is your household, or anyone you share family recipes with. Invite people to it,
      then share private family collections with it from each collection's page. Joining a group
      shares nothing by itself.
    </p>
    <p v-if="user === null" class="status"><a href="/api/auth/login">Sign in</a> to see yours.</p>
    <template v-else-if="user">
      <p v-if="failed" role="alert">Your groups couldn't be loaded. Try reloading the page.</p>
      <p v-else-if="!groups" class="status">Loading…</p>
      <ul v-else-if="groups.length" class="recipe-list">
        <li v-for="g in groups" :key="g.id">
          <a :href="`/groups/${g.id}`">{{ g.name }}</a>
          <span class="page-ref"
            >{{ g.members }} {{ g.members === 1 ? "member" : "members" }} ·
            {{ ROLE_NAMES[g.role] }}</span
          >
        </li>
      </ul>
      <p v-else class="status">You aren't in a group yet.</p>

      <form class="recipe-form" @submit.prevent="make">
        <label for="group-name">Make a group</label>
        <input
          id="group-name"
          v-model="name"
          required
          maxlength="100"
          placeholder="The Tetzloff family"
        />
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button type="submit" class="primary">Make the group</button>
      </form>
    </template>
  </article>
</template>
