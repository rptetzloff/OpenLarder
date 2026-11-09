<script setup lang="ts">
import { computed, ref } from "vue";
import { type Side, type Suggestion, decide } from "../suggestions";

// One suggestion, with Accept and Dismiss while it's open.
const props = defineProps<{ suggestion: Suggestion }>();
const emit = defineEmits<{ decided: [suggestion: Suggestion] }>();

// Followed, not copied: once decided, the page hands back the new state.
const s = computed(() => props.suggestion);
// For a merge, the name to keep: the model's choice until changed.
const keep = ref<"a" | "b">(props.suggestion.keep ?? "a");
const error = ref("");
const busy = ref(false);

// For "one under another": which goes under which.
const child = computed(() => (s.value.decision === "b_under_a" ? s.value.b : s.value.a));
const parent = computed(() => (s.value.decision === "b_under_a" ? s.value.a : s.value.b));
const gone = computed(() => [s.value.a, s.value.b].some((side) => side && !side.exists));

function uses(side: Side) {
  return side.recipes === 1 ? "1 recipe" : `${side.recipes.toLocaleString()} recipes`;
}

async function act(action: "accept" | "dismiss") {
  busy.value = true;
  error.value = "";
  try {
    const { id, kind } = s.value;
    emit("decided", await decide(id, action, kind === "merge" ? keep.value : undefined));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <li class="flag suggestion">
    <template v-if="s.kind === 'merge' && s.a && s.b">
      <p class="flag-what"><strong>Same ingredient?</strong></p>
      <fieldset v-if="s.status === 'open' && s.actionable" class="keep-name">
        <legend>Keep the name</legend>
        <label v-for="side in (['a', 'b'] as const)" :key="side">
          <input v-model="keep" type="radio" :name="`keep-${s.id}`" :value="side" />
          <a :href="`/ingredients/${s[side]!.id}`">{{ s[side]!.name }}</a>
          <span class="status"> · {{ uses(s[side]!) }}</span>
        </label>
      </fieldset>
      <p v-else>
        <a v-if="s.a.exists" :href="`/ingredients/${s.a.id}`">{{ s.a.name }}</a>
        <span v-else>{{ s.a.name }} (gone)</span>
        and
        <a v-if="s.b.exists" :href="`/ingredients/${s.b.id}`">{{ s.b.name }}</a>
        <span v-else>{{ s.b.name }} (gone)</span>
      </p>
    </template>
    <template v-else-if="s.kind === 'parent' && child && parent">
      <p class="flag-what"><strong>One under another?</strong></p>
      <p>
        <a v-if="child.exists" :href="`/ingredients/${child.id}`">{{ child.name }}</a>
        <span v-else>{{ child.name }} (gone)</span>
        goes under
        <a v-if="parent.exists" :href="`/ingredients/${parent.id}`">{{ parent.name }}</a>
        <span v-else>{{ parent.name }} (gone)</span>
      </p>
    </template>
    <p v-else class="flag-what"><strong>{{ s.kind }}</strong></p>
    <p v-if="s.reason" class="suggestion-reason">{{ s.reason }}</p>
    <p class="byline">
      <span v-if="s.similarity !== null">{{ Math.round(s.similarity * 100) }}% alike · </span>
      {{ s.model }}, {{ s.prompt_version }}
    </p>
    <p v-if="s.status !== 'open'" class="status">
      {{ s.status === "accepted" ? "Accepted" : "Dismissed" }}
      {{ new Date(s.decided_at!).toLocaleDateString() }}
    </p>
    <template v-else>
      <p v-if="gone" class="status">
        An ingredient this names has been merged or deleted since, so it can only be dismissed.
      </p>
      <p v-else-if="!s.actionable" class="status">This can't be accepted here yet.</p>
      <div class="admin-actions">
        <button v-if="s.actionable" type="button" class="link" :disabled="busy" @click="act('accept')">
          Accept
        </button>
        <button type="button" class="link" :disabled="busy" @click="act('dismiss')">Dismiss</button>
      </div>
    </template>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </li>
</template>
