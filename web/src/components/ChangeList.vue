<script setup lang="ts">
import { type Change, cameThrough, label, madeBy, shown } from "../history";

// Changes, newest first, each with what it added, changed or removed.
defineProps<{ changes: Change[]; linkSources?: boolean }>();
const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
</script>

<template>
  <ol class="change-list">
    <li v-for="c in changes" :key="c.id">
      <p class="change-head">
        <strong>{{ madeBy(c) }}</strong>
        <span class="muted">
          · <time :datetime="c.at">{{ when(c.at) }}</time>
          <template v-if="cameThrough(c.via)"> · through {{ cameThrough(c.via) }}</template>
          <template v-if="linkSources && c.source_id">
            · <a :href="`/sources/${c.source_id}`">the source</a>
          </template>
        </span>
      </p>
      <ul class="change-entries">
        <li v-for="(e, i) in c.entries" :key="i">
          <span class="change-action" :class="e.action">{{ e.action }}</span>{{ " " }}
          {{ e.what }}{{ e.name ? ` ${shown(e.name)}` : "" }}
          <ul v-if="e.action === 'changed' && e.fields.length" class="change-fields">
            <li v-for="f in e.fields" :key="f.field">
              {{ label(f.field) }}: {{ shown(f.before) }} → {{ shown(f.after) }}
            </li>
          </ul>
        </li>
      </ul>
    </li>
  </ol>
</template>
