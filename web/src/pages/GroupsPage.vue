<script setup lang="ts">
import SignInLink from "../components/SignInLink.vue";
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
  <article class="wide">
    <div class="list-head">
      <h1>Groups</h1>
      <p class="muted">
        A group is your household, or anyone you share family recipes with. Invite people to it,
        then share private family collections with it from each collection's page. Joining a group
        shares nothing by itself.
      </p>
    </div>
    <p v-if="user === null" class="status"><SignInLink /> to see yours.</p>
    <template v-else-if="user">
      <div class="add-panels">
        <details class="add-panel" :open="groups?.length === 0 || undefined">
          <summary>Make a group</summary>
          <form class="recipe-form group-form" @submit.prevent="make">
            <label for="group-name">What it's called</label>
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
        </details>
      </div>
      <p v-if="failed" role="alert">Your groups couldn't be loaded. Try reloading the page.</p>
      <p v-else-if="!groups" class="status">Loading…</p>
      <table v-else-if="groups.length" class="recipe-table group-table">
        <thead>
          <tr>
            <th scope="col">Group</th>
            <th scope="col">You</th>
            <th scope="col" class="numeric">Members</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="g in groups" :key="g.id">
            <td><a :href="`/groups/${g.id}`" class="strong">{{ g.name }}</a></td>
            <td><span class="cell-label">You: </span>{{ ROLE_NAMES[g.role] }}</td>
            <td class="numeric">
              {{ g.members.toLocaleString() }}<span class="cell-label">
                {{ g.members === 1 ? " member" : " members" }}</span
              >
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="status">You aren't in a group yet.</p>
    </template>
  </article>
</template>
