<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  cancelInvite,
  deleteGroup,
  getGroup,
  type Group,
  makeInvite,
  removeMember,
  renameGroup,
  type Role,
  ROLE_NAMES,
  setRole,
} from "../groups";
import type { Me } from "../me";

const props = defineProps<{ id: string; user: Me | null | undefined }>();

const group = ref<Group | null>(null);
const missing = ref(false);
const error = ref("");
const isAdmin = computed(() => group.value?.role === "admin");
const ROLES = Object.keys(ROLE_NAMES) as Role[];

async function load() {
  try {
    group.value = await getGroup(props.id);
    document.title = `${group.value.name} · OpenLarder`;
  } catch {
    missing.value = true;
  }
}
onMounted(load);

// Any change: do it, then show the group as it now is, or say why not.
async function act(change: () => Promise<unknown>) {
  error.value = "";
  try {
    await change();
    await load();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

const renaming = ref(false);
const newName = ref("");
const rename = () =>
  act(async () => {
    await renameGroup(props.id, newName.value);
    renaming.value = false;
  });

// The link is shown once, as made; only its hash is kept.
const inviteRole = ref<Role>("view");
const link = ref<{ url: string; expires: string } | null>(null);
const copied = ref(false);
const invite = () =>
  act(async () => {
    const made = await makeInvite(props.id, inviteRole.value);
    link.value = {
      url: `${location.origin}/invite/${made.token}`,
      expires: new Date(made.expires_at).toLocaleDateString(undefined, { dateStyle: "long" }),
    };
    copied.value = false;
  });
async function copy() {
  try {
    await navigator.clipboard.writeText(link.value!.url);
    copied.value = true;
  } catch {
    // Selecting the text is the fallback; the field is there to select.
  }
}

const isMe = (userId: string) => props.user?.id === userId;
function leave() {
  if (!confirm(`Leave ${group.value!.name}? Your collections stop being shared with it.`)) return;
  error.value = "";
  removeMember(props.id, props.user!.id)
    .then(() => (location.href = "/groups"))
    .catch((e) => (error.value = e instanceof Error ? e.message : String(e)));
}
function remove(member: Group["members"][number]) {
  if (!confirm(`Remove ${member.name ?? "them"} from ${group.value!.name}?`)) return;
  act(() => removeMember(props.id, member.user_id));
}
function destroy() {
  if (!confirm(`Delete ${group.value!.name}? The collections stay with their owners.`)) return;
  error.value = "";
  deleteGroup(props.id)
    .then(() => (location.href = "/groups"))
    .catch((e) => (error.value = e instanceof Error ? e.message : String(e)));
}
</script>

<template>
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/groups">Groups</a>
      <template v-if="group">
        <span aria-hidden="true">›</span>
        <span aria-current="page">{{ group.name }}</span>
      </template>
    </nav>
    <p v-if="missing">There's no group here, or you aren't in it.</p>
    <p v-else-if="!group" class="status">Loading…</p>
    <template v-else>
      <div class="list-head group-head">
        <div>
          <h1>{{ group.name }}</h1>
          <p class="muted">You: {{ ROLE_NAMES[group.role] }}</p>
        </div>
        <div v-if="isAdmin && !renaming" class="row-actions">
          <button
            type="button"
            class="secondary small"
            @click="
              newName = group.name;
              renaming = true;
            "
          >
            Rename
          </button>
          <button type="button" class="secondary small" @click="destroy">Delete the group</button>
        </div>
      </div>
      <form v-if="isAdmin && renaming" class="inline-form" @submit.prevent="rename">
        <label for="group-rename" class="visually-hidden">New name</label>
        <input id="group-rename" v-model="newName" required maxlength="100" />
        <button type="submit" class="primary">Rename</button>
        <button type="button" class="link" @click="renaming = false">Cancel</button>
      </form>
      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <div class="group-layout">
        <div>
          <h2 class="section-title">Shared with the group</h2>
          <table v-if="group.collections.length" class="recipe-table">
            <thead>
              <tr>
                <th scope="col">Collection</th>
                <th scope="col">Whose</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in group.collections" :key="c.id">
                <td><a :href="`/sources/${c.id}`" class="strong">{{ c.title }}</a></td>
                <td>
                  <span class="cell-label">Whose: </span
                  >{{ c.owner_name ?? "Someone without a name yet" }}
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="status">
            Nothing yet. Each owner shares a private family collection from its page.
          </p>

          <h2 class="section-title">Members</h2>
          <table class="recipe-table member-table">
            <thead>
              <tr>
                <th scope="col">Member</th>
                <th scope="col">Role</th>
                <th v-if="isAdmin" scope="col"><span class="visually-hidden">Remove</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in group.members" :key="m.user_id">
                <td>
                  {{ m.name ?? "Someone without a name yet" }}{{ isMe(m.user_id) ? " (you)" : "" }}
                </td>
                <td>
                  <template v-if="isAdmin">
                    <label :for="`role-${m.user_id}`" class="visually-hidden"
                      >Role of {{ m.name ?? "this member" }}</label
                    >
                    <select
                      :id="`role-${m.user_id}`"
                      :value="m.role"
                      @change="
                        act(() =>
                          setRole(id, m.user_id, ($event.target as HTMLSelectElement).value as Role),
                        )
                      "
                    >
                      <option v-for="r in ROLES" :key="r" :value="r">{{ ROLE_NAMES[r] }}</option>
                    </select>
                  </template>
                  <template v-else>{{ ROLE_NAMES[m.role] }}</template>
                </td>
                <td v-if="isAdmin">
                  <button
                    v-if="!isMe(m.user_id)"
                    type="button"
                    class="secondary small"
                    @click="remove(m)"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <p class="row-actions">
            <button type="button" class="secondary small" @click="leave">Leave the group</button>
          </p>
        </div>

        <section v-if="isAdmin" class="tool-panel" aria-labelledby="invite-title">
          <h2 id="invite-title">Invite someone</h2>
          <form class="recipe-form" @submit.prevent="invite">
            <label for="invite-role">They join as</label>
            <select id="invite-role" v-model="inviteRole">
              <option v-for="r in ROLES" :key="r" :value="r">{{ ROLE_NAMES[r] }}</option>
            </select>
            <p class="help">A link for one person. It works once and expires in 7 days.</p>
            <button type="submit" class="primary">Make a link</button>
          </form>
          <div v-if="link" class="notice" role="status">
            <p>
              Send this to them. It won't be shown again; it works once, until {{ link.expires }}.
            </p>
            <div class="inline-form">
              <label for="invite-link" class="visually-hidden">Invite link</label>
              <input
                id="invite-link"
                :value="link.url"
                readonly
                @focus="($event.target as HTMLInputElement).select()"
              />
              <button type="button" class="primary" @click="copy">
                {{ copied ? "Copied" : "Copy" }}
              </button>
            </div>
          </div>
          <template v-if="group.invites.length">
            <h3>Waiting to be used</h3>
            <ul class="invite-list">
              <li v-for="i in group.invites" :key="i.id">
                {{ ROLE_NAMES[i.role] }}
                <span class="muted"
                  >until
                  {{
                    new Date(i.expires_at).toLocaleDateString(undefined, { dateStyle: "long" })
                  }}</span
                >
                <button type="button" class="link" @click="act(() => cancelInvite(id, i.id))">
                  Cancel
                </button>
              </li>
            </ul>
          </template>
        </section>
      </div>
    </template>
  </article>
</template>
