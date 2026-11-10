<script setup lang="ts">
import { computed, ref } from "vue";
import { addTag, KINDS, listTags, type Tag, type TagKind } from "../tags";

// Choosing a recipe's or a source's tags from the fixed list, for whoever
// may change it. Tags from the source show ticked and can't be changed here.
// An admin can add a tag to the list.
const props = defineProps<{
  // What it's called in "Tags for this …".
  what: string;
  selected: string[];
  // Set on the source, for a recipe.
  inherited?: string[];
  canAdd: boolean;
  save: (ids: string[]) => Promise<unknown>;
}>();

const open = ref(false);
const all = ref<Tag[] | null>(null);
const chosen = ref<string[]>([]);
const error = ref("");
const busy = ref(false);
const newKind = ref<TagKind>("course");
const newName = ref("");

const byKind = computed(() =>
  KINDS.map((k) => ({ ...k, tags: (all.value ?? []).filter((t) => t.kind === k.kind) })).filter(
    (k) => k.tags.length,
  ),
);
const fromSource = (id: string) => props.inherited?.includes(id) ?? false;

async function toggleOpen(event: Event) {
  open.value = (event.target as HTMLDetailsElement).open;
  if (!open.value) return;
  chosen.value = [...props.selected];
  error.value = "";
  if (!all.value) {
    try {
      all.value = await listTags();
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }
}

function toggle(id: string) {
  chosen.value = chosen.value.includes(id)
    ? chosen.value.filter((c) => c !== id)
    : [...chosen.value, id];
}

async function act(work: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  try {
    await work();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

const submit = () => act(async () => void (await props.save(chosen.value)));
const add = () =>
  act(async () => {
    const tag = await addTag(newKind.value, newName.value);
    all.value = [...(all.value ?? []), tag];
    chosen.value = [...chosen.value, tag.id];
    newName.value = "";
  });
</script>

<template>
  <details class="add-panel tag-editor" @toggle="toggleOpen">
    <summary>Edit tags</summary>
    <form @submit.prevent="submit">
      <p v-if="!all && !error" class="status">Loading…</p>
      <fieldset v-for="k in byKind" :key="k.kind" class="tag-kind">
        <legend>{{ k.label }}</legend>
        <div class="kind-filter">
          <button
            v-for="t in k.tags"
            :key="t.id"
            type="button"
            class="secondary small"
            :aria-pressed="chosen.includes(t.id) || fromSource(t.id)"
            :disabled="fromSource(t.id)"
            :title="fromSource(t.id) ? 'From the source: change it there' : undefined"
            @click="toggle(t.id)"
          >
            {{ t.name }}
          </button>
        </div>
      </fieldset>
      <p v-if="inherited?.length" class="help">
        Tags from the source are ticked and greyed: change them on the source's page.
      </p>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" class="primary" :disabled="busy || !all">
        Save the tags for this {{ what }}
      </button>
    </form>
    <form v-if="canAdd && all" class="tag-new" @submit.prevent="add">
      <label for="tag-new-kind">Add a tag to the list</label>
      <div class="row-actions">
        <select id="tag-new-kind" v-model="newKind" aria-label="Kind">
          <option v-for="k in KINDS" :key="k.kind" :value="k.kind">{{ k.label }}</option>
        </select>
        <input v-model="newName" aria-label="New tag" maxlength="60" placeholder="Georgian" required />
        <button type="submit" class="secondary small" :disabled="busy">Add</button>
      </div>
    </form>
  </details>
</template>
