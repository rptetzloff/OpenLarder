<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { type IsSaved, isSaved, type OtherList, save, type State, unsave } from "../saved";

// A recipe's "Want to cook" (routers/saved.py): saved as wanted, marked
// cooked, or taken off. Lists shared with you say whether it's on them;
// those you may change take it too.
const props = defineProps<{ recipeId: string }>();

const state = ref<IsSaved | null>(null);
const busy = ref(false);
const error = ref("");
const name = (o: OtherList) => `${o.owner_name ?? "Someone"}'s list`;
const theirs = computed(() => (state.value?.others ?? []).filter((o) => o.state));
const addable = computed(() => (state.value?.others ?? []).filter((o) => !o.state && o.editable));

onMounted(async () => {
  try {
    state.value = await isSaved(props.recipeId);
  } catch {
    // Shown as not saved; saving says what's wrong.
    state.value = { recipe_id: props.recipeId, state: null, others: [] };
  }
});

async function act(job: () => Promise<IsSaved | void>) {
  busy.value = true;
  error.value = "";
  try {
    state.value = (await job()) ?? (await isSaved(props.recipeId));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

const put = (to: State, owner?: string) => act(() => save(props.recipeId, to, owner));
const remove = (owner?: string) => act(() => unsave(props.recipeId, owner));
</script>

<template>
  <div v-if="state" class="save-button">
    <template v-if="state.state">
      <p>
        <span aria-hidden="true">✓</span>
        {{ state.state === "want" ? "You want to cook this." : "You've cooked this." }}
        <a href="/saved">Saved recipes</a>
      </p>
      <p class="save-actions">
        <button
          type="button"
          class="link"
          :disabled="busy"
          @click="put(state.state === 'want' ? 'cooked' : 'want')"
        >
          {{ state.state === "want" ? "I've cooked it" : "I want to cook it again" }}
        </button>
        <button type="button" class="link" :disabled="busy" @click="remove()">
          Take it off my list
        </button>
      </p>
    </template>
    <button v-else type="button" class="secondary" :disabled="busy" @click="put('want')">
      Want to cook
    </button>
    <ul v-if="theirs.length || addable.length" class="save-others">
      <li v-for="o in theirs" :key="o.owner_id">
        <span aria-hidden="true">✓</span> On <a href="/saved">{{ name(o) }}</a
        >{{ o.state === "cooked" ? ", cooked" : "" }}.
        <template v-if="o.editable">
          <button
            type="button"
            class="link"
            :disabled="busy"
            :aria-label="`${o.state === 'want' ? 'Cooked' : 'Want again'}, on ${name(o)}`"
            @click="put(o.state === 'want' ? 'cooked' : 'want', o.owner_id)"
          >
            {{ o.state === "want" ? "Cooked" : "Want again" }}
          </button>
          <button
            type="button"
            class="link"
            :disabled="busy"
            :aria-label="`Take it off ${name(o)}`"
            @click="remove(o.owner_id)"
          >
            Take it off
          </button>
        </template>
      </li>
      <li v-for="o in addable" :key="o.owner_id">
        <button type="button" class="link" :disabled="busy" @click="put('want', o.owner_id)">
          Save it to {{ name(o) }}
        </button>
      </li>
    </ul>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.save-button {
  margin: 0.5rem 0 1rem;
}
.save-button p {
  margin: 0;
}
.save-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
}
.save-others {
  list-style: none;
  padding: 0;
  margin: 0.35rem 0 0;
  display: grid;
  gap: 0.2rem;
}
.save-others .link {
  margin-left: 0.5rem;
}
.save-others li > .link:first-child {
  margin-left: 0;
}
</style>
