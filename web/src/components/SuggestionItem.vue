<script setup lang="ts">
import { computed, ref } from "vue";
import { type Side, type Suggestion, acceptForSource, decide } from "../suggestions";

// One suggestion, with Accept and Dismiss while it's open.
const props = defineProps<{ suggestion: Suggestion }>();
const emit = defineEmits<{
  decided: [suggestion: Suggestion];
  // Several were accepted at once: how many, for the page to say and to
  // load again.
  together: [done: number];
}>();

// Followed, not copied: once decided, the page hands back the new state.
const s = computed(() => props.suggestion);
// For a merge, the name to keep: the model's choice until changed.
const keep = ref<"a" | "b">(props.suggestion.keep ?? "a");
const error = ref("");
const busy = ref(false);

// For "one under another": which goes under which.
const child = computed(() => (s.value.decision === "b_under_a" ? s.value.b : s.value.a));
const parent = computed(() => (s.value.decision === "b_under_a" ? s.value.a : s.value.b));
const gone = computed(
  () =>
    [s.value.a, s.value.b].some((side) => side && !side.exists) ||
    (s.value.kind === "tag" && !(s.value.recipe?.exists && s.value.tag?.exists)) ||
    (s.value.kind === "equipment" && !(s.value.recipe?.exists && s.value.equipment?.exists)) ||
    (s.value.kind === "allergen" && !s.value.allergen?.exists) ||
    (!!s.value.title && !(s.value.title.exists && s.value.title.unchanged)),
);

function uses(side: Side) {
  return side.recipes === 1 ? "1 recipe" : `${side.recipes.toLocaleString()} recipes`;
}

// A book about one appliance has this suggestion for each of its recipes:
// all of them, in one decision.
const inSource = computed(() => (s.value.equipment?.others_in_source ?? 0) + 1);
async function acceptAll() {
  const { equipment, recipe, id } = s.value;
  const asked =
    `Add ${equipment!.name} to all ${inSource.value} recipes of “${recipe!.source_title}” ` +
    "it's suggested for?";
  if (!confirm(asked)) return;
  busy.value = true;
  error.value = "";
  try {
    emit("together", (await acceptForSource(id)).done);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
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
  <li class="suggestion">
    <template v-if="s.kind === 'merge' && s.a && s.b">
      <h2>Same ingredient?</h2>
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
      <h2>Does one count as the other?</h2>
      <p>
        <a v-if="child.exists" :href="`/ingredients/${child.id}`">{{ child.name }}</a>
        <span v-else>{{ child.name }} (gone)</span>
        counts as
        <a v-if="parent.exists" :href="`/ingredients/${parent.id}`">{{ parent.name }}</a>
        <span v-else>{{ parent.name }} (gone)</span>
      </p>
    </template>
    <template v-else-if="s.kind === 'tag' && s.recipe && s.tag">
      <h2>Tag it {{ s.tag.name }}?</h2>
      <p>
        <a v-if="s.recipe.exists" :href="`/recipes/${s.recipe.id}`">{{ s.recipe.title }}</a>
        <span v-else>{{ s.recipe.title }} (gone)</span>
        <template v-if="s.recipe.source_title">
          in <a :href="`/sources/${s.recipe.source_id}`">{{ s.recipe.source_title }}</a></template
        ><template v-if="s.recipe.chapter">, “{{ s.recipe.chapter }}”</template>
      </p>
      <p>
        <span class="tag-chip">{{ s.tag.name }}</span>
        <span class="muted"> · {{ s.tag.kind }}</span>
        <span v-if="s.tag.already" class="muted"> · it has this tag already</span>
        <span v-if="!s.tag.exists" class="muted"> (gone)</span>
      </p>
    </template>
    <!-- Equipment a rule says a recipe probably needs (Ray's equipment
         spec, 2026-11-15), laid out as a tag for a recipe is. -->
    <template v-else-if="s.kind === 'equipment' && s.recipe && s.equipment">
      <!-- As the search's chip words it: the names don't all take an article. -->
      <h2>Needs {{ s.equipment.name }}?</h2>
      <p>
        <a v-if="s.recipe.exists" :href="`/recipes/${s.recipe.id}`">{{ s.recipe.title }}</a>
        <span v-else>{{ s.recipe.title }} (gone)</span>
        <template v-if="s.recipe.source_title">
          in <a :href="`/sources/${s.recipe.source_id}`">{{ s.recipe.source_title }}</a></template
        ><template v-if="s.recipe.chapter">, “{{ s.recipe.chapter }}”</template>
      </p>
      <p>
        <a v-if="s.equipment.exists" :href="`/equipment/${s.equipment.id}`">{{
          s.equipment.name
        }}</a>
        <span v-else>{{ s.equipment.name }}</span>
        <span v-if="s.equipment.already" class="muted"> · it needs this already</span>
      </p>
    </template>
    <template v-else-if="s.kind === 'allergen' && s.a && s.allergen">
      <h2>
        {{ s.allergen.status === "contains" ? "Contains" : "May contain" }}
        {{ s.allergen.label.toLowerCase() }}?
      </h2>
      <p>
        <a v-if="s.a.exists" :href="`/ingredients/${s.a.id}`">{{ s.a.name }}</a>
        <span v-else>{{ s.a.name }} (gone)</span>
        <span class="status"> · {{ uses(s.a) }}</span>
        <span v-if="s.allergen.already" class="muted">
          · it records something about {{ s.allergen.label.toLowerCase() }} already</span
        >
      </p>
    </template>
    <template v-else-if="s.title">
      <h2>
        {{ s.kind === "title_case" ? "Capitals in this title?" : "An apostrophe in this title?" }}
      </h2>
      <!-- Both in full, one under the other, so the change can be read. -->
      <dl class="title-change">
        <div>
          <dt>Now</dt>
          <dd>
            <a v-if="s.title.exists" :href="`/sources/${s.title.source_id}`">{{
              s.title.was
            }}</a>
            <span v-else>{{ s.title.was }} (gone)</span>
          </dd>
        </div>
        <div>
          <dt>Suggested</dt>
          <dd>{{ s.title.proposed }}</dd>
        </div>
      </dl>
    </template>
    <h2 v-else>{{ s.kind }}</h2>
    <p v-if="s.reason" class="suggestion-reason">{{ s.reason }}</p>
    <p class="byline">
      <span v-if="s.certainty" :class="['certainty', s.certainty === 'certain' ? 'tone-ok' : 'tone-info']">{{ s.certainty === "certain" ? "Certain" : "Likely" }}</span>
      <span v-if="s.certainty"> · </span>
      <span v-if="s.similarity !== null">{{ Math.round(s.similarity * 100) }}% alike · </span>
      {{ s.model }}, {{ s.prompt_version }}
    </p>
    <p v-if="s.status !== 'open'" class="status">
      {{ s.status === "accepted" ? "Accepted" : "Dismissed" }}
      {{ new Date(s.decided_at!).toLocaleDateString() }}
    </p>
    <template v-else>
      <p v-if="gone" class="status">
        {{
          s.title
            ? s.title.exists
              ? "The title has been changed since, so this can only be dismissed."
              : "The book has been deleted since, so this can only be dismissed."
            : s.kind === "tag"
            ? "Its recipe or its tag has been deleted since, so it can only be dismissed."
            : s.kind === "equipment"
            ? "Its recipe has gone, or its equipment isn't in the list any more, so it can only be dismissed."
            : s.kind === "allergen" && s.a?.exists
              ? "That allergen isn't on the list any more, so it can only be dismissed."
              : "An ingredient this names has been merged or deleted since, so it can only be dismissed."
        }}
      </p>
      <p v-else-if="!s.actionable" class="status">This can't be accepted here yet.</p>
      <div class="row-actions">
        <button v-if="s.actionable" type="button" class="primary small" :disabled="busy" @click="act('accept')">
          Accept
        </button>
        <button
          v-if="s.actionable && s.equipment?.others_in_source"
          type="button"
          class="secondary small accept-source"
          :disabled="busy"
          @click="acceptAll"
        >
          Accept for all {{ inSource }} in this source
        </button>
        <button type="button" class="secondary small" :disabled="busy" @click="act('dismiss')">
          Dismiss
        </button>
      </div>
    </template>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </li>
</template>

<style scoped>
.title-change {
  margin: 0.25rem 0 0.5rem;
}
.title-change div {
  display: flex;
  gap: 0.5rem;
}
.title-change dt {
  flex: 0 0 5.5rem;
  color: var(--muted);
}
.title-change dd {
  margin: 0;
  min-width: 0;
}
</style>
