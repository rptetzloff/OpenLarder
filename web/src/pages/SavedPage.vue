<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { whereItIs } from "../ingredients";
import type { Me } from "../me";
import { mySaved, save, type Saved, type SavedRecipe, shareSaved, type State, unsave } from "../saved";

// Saved recipes (routers/saved.py): what you want to cook and what you
// have, then the lists shared with you. SCOPING.md: "Saves, likes, 'want to
// cook' lists"; shared with household groups as the shelf is.
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Saved recipes · OpenLarder";

const saved = ref<Saved | null>(null);
const error = ref("");
const busy = ref(false);
const sharing = ref(false);
// Want to cook, or cooked.
const tab = ref<State>("want");

// Yours, then each shared with you: one layout for both.
const lists = computed(() =>
  saved.value
    ? [
        { key: "mine", owner: undefined, title: "", note: "", editable: true, recipes: saved.value.recipes },
        ...saved.value.shared.map((s) => ({
          key: s.owner_id,
          owner: s.owner_id as string | undefined,
          title: `${s.owner_name ?? "Someone"}'s list`,
          note: `Shared with you through ${s.through.map((g) => g.name).join(", ")}${
            s.editable ? "" : ": you can see it, not change it"
          }.`,
          editable: s.editable,
          recipes: s.recipes,
        })),
      ]
    : [],
);
const every = computed(() => lists.value.flatMap((l) => l.recipes));
const count = (state: State) => new Set(every.value.filter((r) => r.state === state).map((r) => r.id)).size;
const of = (recipes: SavedRecipe[]) => recipes.filter((r) => r.state === tab.value);

async function act(work: () => Promise<Saved | unknown>) {
  busy.value = true;
  error.value = "";
  try {
    await work();
    saved.value = await mySaved();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

const move = (r: SavedRecipe, owner?: string) =>
  act(() => save(r.id, r.state === "want" ? "cooked" : "want", owner));
const remove = (r: SavedRecipe, owner?: string) => act(() => unsave(r.id, owner));
function toggleGroup(groupId: string, on: boolean) {
  const ids = new Set(saved.value!.shared_with.map((g) => g.id));
  if (on) ids.add(groupId);
  else ids.delete(groupId);
  act(() => shareSaved([...ids]));
}

watch(
  () => props.user,
  (user) => {
    if (user && !saved.value) act(async () => {});
  },
  { immediate: true },
);
</script>

<template>
  <article class="wide saved-page">
    <div class="list-head">
      <h1>Saved recipes</h1>
      <p class="muted">
        The recipes you want to cook, and the ones you have. Only you see them, and the household
        <a href="/groups">groups</a> you share them with. To save one, open its page and choose
        “Want to cook”.
      </p>
    </div>
    <p v-if="user === null" class="status">
      <a href="/api/auth/login">Sign in</a> to save recipes.
    </p>
    <template v-else-if="user">
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="!saved && !error" class="status">Loading…</p>
      <template v-else-if="saved">
        <div class="saved-tools">
          <div class="kind-filter" role="group" aria-label="Which recipes">
            <button type="button" class="secondary small" :aria-pressed="tab === 'want'" @click="tab = 'want'">
              Want to cook <span class="count">{{ count("want").toLocaleString() }}</span>
            </button>
            <button type="button" class="secondary small" :aria-pressed="tab === 'cooked'" @click="tab = 'cooked'">
              Cooked <span class="count">{{ count("cooked").toLocaleString() }}</span>
            </button>
          </div>
          <a v-if="every.length" href="/search?sv=1" class="button-outline">Search my saved recipes</a>
        </div>
        <section v-for="l in lists" :key="l.key" class="saved-section">
          <template v-if="l.owner">
            <h2>{{ l.title }}</h2>
            <p class="muted">{{ l.note }}</p>
          </template>
          <template v-else>
            <p v-if="saved.groups.length" class="saved-sharing">
              <span v-if="saved.shared_with.length && !sharing" class="muted"
                >Shared with {{ saved.shared_with.map((g) => g.name).join(", ") }}.</span
              >
              <button type="button" class="link" :aria-expanded="sharing" @click="sharing = !sharing">
                Share
              </button>
            </p>
            <fieldset v-if="sharing" class="larder-share">
              <legend>Who else sees them</legend>
              <label v-for="g in saved.groups" :key="g.id" class="check">
                <input
                  type="checkbox"
                  :checked="saved.shared_with.some((x) => x.id === g.id)"
                  :disabled="busy"
                  @change="toggleGroup(g.id, ($event.target as HTMLInputElement).checked)"
                />
                {{ g.name }}
              </label>
              <p class="help">
                Its members see your saved recipes; editors and admins of the group change what's
                on the list.
              </p>
            </fieldset>
          </template>
          <p v-if="!of(l.recipes).length" class="status">
            <template v-if="tab === 'want'">
              {{ l.owner ? "Nothing they want to cook yet." : "Nothing you want to cook yet." }}
              <template v-if="!l.owner"> <a href="/search">Search</a> for something.</template>
            </template>
            <template v-else>Nothing marked cooked yet.</template>
          </p>
          <ul v-else class="hits">
            <li v-for="r in of(l.recipes)" :key="r.id" class="hit">
              <img v-if="r.cover_url" :src="r.cover_url" alt="" class="hit-cover" loading="lazy" />
              <span v-else class="hit-cover" aria-hidden="true"></span>
              <div>
                <h3><a :href="`/recipes/${r.id}`">{{ r.title }}</a></h3>
                <p class="hit-where">
                  <a :href="`/sources/${r.source_id}`">{{ r.source_title }}</a
                  ><template v-if="whereItIs(r)"> · {{ whereItIs(r) }}</template>
                </p>
                <p v-if="l.editable" class="saved-actions">
                  <button
                    type="button"
                    class="link"
                    :disabled="busy"
                    :aria-label="`${r.state === 'want' ? 'Cooked it' : 'Want to cook again'}: ${r.title}`"
                    @click="move(r, l.owner)"
                  >
                    {{ r.state === "want" ? "Cooked it" : "Want to cook again" }}
                  </button>
                  <button
                    type="button"
                    class="link"
                    :disabled="busy"
                    :aria-label="`Take off ${r.title}`"
                    @click="remove(r, l.owner)"
                  >
                    Take off
                  </button>
                </p>
              </div>
            </li>
          </ul>
        </section>
      </template>
    </template>
  </article>
</template>

<style scoped>
.saved-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  margin-bottom: 1rem;
}
.saved-section + .saved-section {
  margin-top: 2rem;
}
.saved-sharing {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.75rem;
  margin: 0 0 0.75rem;
}
.saved-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1rem;
}
</style>
