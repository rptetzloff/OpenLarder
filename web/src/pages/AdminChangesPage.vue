<script setup lang="ts">
import { computed, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import ChangeList from "../components/ChangeList.vue";
import { type Change, recentChanges } from "../history";
import type { Me } from "../me";

// The latest changes to the catalog, for moderators. *Ray, 2026-11-10.*
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Recent changes · Admin · OpenLarder";

const allowed = computed(() => !!props.user?.may_edit);
const by = ref(new URLSearchParams(location.search).get("by") ?? "");
const changes = ref<Change[] | null>(null);
const error = ref("");

async function load() {
  error.value = "";
  changes.value = null;
  try {
    changes.value = await recentChanges(by.value.trim());
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

watch(allowed, (yes) => yes && !changes.value && load(), { immediate: true });
</script>

<template>
  <AdminBar v-if="user?.may_edit" :user="user" current="/admin/changes" />
  <article class="wide">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="/admin">Admin</a>
      <span aria-hidden="true">›</span>
      <span aria-current="page">Recent changes</span>
    </nav>
    <div class="list-head">
      <h1>Recent changes</h1>
      <p class="muted">
        Everything added, changed or removed in the catalog, newest first, by whom. Family
        collections aren't listed here. Each source, recipe, ingredient and author also shows its
        own history on its page.
      </p>
    </div>
    <p v-if="!user?.may_edit" class="status">This is for moderators.</p>
    <template v-else>
      <form class="inline-form" role="search" @submit.prevent="load">
        <label for="changes-by" class="visually-hidden">Only changes by</label>
        <input id="changes-by" v-model="by" maxlength="32" placeholder="Only changes by (a display name)" />
        <button type="submit" class="primary">Show</button>
        <button v-if="by" type="button" class="secondary" @click="(by = ''), load()">Everyone's</button>
      </form>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-else-if="!changes" class="status">Loading…</p>
      <ChangeList v-else-if="changes.length" :changes="changes" link-sources />
      <p v-else class="status">No changes recorded{{ by ? " by that name" : "" }} yet.</p>
    </template>
  </article>
</template>
