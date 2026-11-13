<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { type AuthorListed, listAuthors } from "../authors";

document.title = "Authors · OpenLarder";

const params = new URLSearchParams(location.search);
const q = ref(params.get("q") ?? "");
// A to Z as the names read, by last name (Ray, 2026-11-12), or the most
// recipes first; everyone, or only people or only organisations.
type Sort = "name" | "surname" | "recipes";
const sort = ref<Sort>(
  (["surname", "recipes"] as const).find((s) => s === params.get("sort")) ?? "name",
);
type Kind = "person" | "organisation";
const kind = ref<Kind | null>(
  (["person", "organisation"] as const).find((k) => k === params.get("kind")) ?? null,
);
const authors = ref<AuthorListed[] | null>(null);
const total = ref(0);
const failed = ref(false);
const loading = ref(false);
// Answers can arrive out of order as someone types; only the latest counts.
let asked = 0;

async function load(more = false) {
  const mine = ++asked;
  loading.value = true;
  failed.value = false;
  try {
    const page = await listAuthors(q.value, more ? (authors.value?.length ?? 0) : 0, {
      sort: sort.value,
      kind: kind.value,
    });
    if (mine !== asked) return;
    authors.value = more ? [...(authors.value ?? []), ...page.authors] : page.authors;
    total.value = page.total;
  } catch {
    if (mine === asked) failed.value = true;
  } finally {
    if (mine === asked) loading.value = false;
  }
}

// The address keeps what's chosen, so a list can be shared.
function remember() {
  const url = new URL(location.href);
  for (const key of ["q", "sort", "kind"]) url.searchParams.delete(key);
  if (q.value.trim()) url.searchParams.set("q", q.value.trim());
  if (sort.value !== "name") url.searchParams.set("sort", sort.value);
  if (kind.value) url.searchParams.set("kind", kind.value);
  history.replaceState(null, "", url);
}

let timer: ReturnType<typeof setTimeout> | undefined;
watch(q, () => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    remember();
    load();
  }, 200);
});
watch([sort, kind], () => {
  remember();
  load();
});
onMounted(() => load());

const KINDS: { value: Kind | null; label: string }[] = [
  { value: null, label: "Everyone" },
  { value: "person", label: "People" },
  { value: "organisation", label: "Organizations" },
];
</script>

<template>
  <article class="wide authors-page">
    <div class="list-head">
      <h1>Authors</h1>
      <p class="muted">
        Everyone credited on a source: authors, editors, photographers, test kitchens. Open one to
        see their sources, or <a href="/sources">browse the sources</a>.
      </p>
    </div>

    <div class="list-tools">
      <div class="list-find">
        <label for="author-filter">Find an author</label>
        <input
          id="author-filter"
          v-model="q"
          type="search"
          autocomplete="off"
          placeholder="Name, as it's printed or filed"
        />
      </div>
      <div class="table-controls">
        <label for="author-sort">Sort</label>
        <select id="author-sort" v-model="sort">
          <option value="name">Name, A to Z</option>
          <option value="surname">Last name, A to Z</option>
          <option value="recipes">Most recipes</option>
        </select>
      </div>
    </div>
    <div class="kind-filter" role="group" aria-label="Kinds">
      <button
        v-for="k in KINDS"
        :key="k.label"
        type="button"
        class="secondary small"
        :aria-pressed="kind === k.value"
        @click="kind = k.value"
      >
        {{ k.label }}
      </button>
    </div>

    <p v-if="failed" role="alert">The authors couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="authors === null" class="status">Loading…</p>
    <p v-else-if="authors.length === 0" class="status">
      {{ q.trim() ? `No author matches “${q.trim()}”.` : "No authors yet." }}
    </p>
    <template v-else>
      <p class="status results-count" role="status">
        {{ total.toLocaleString() }}
        {{
          kind === "organisation"
            ? total === 1
              ? "organization"
              : "organizations"
            : kind === "person"
              ? total === 1
                ? "person"
                : "people"
              : total === 1
                ? "author"
                : "authors"
        }}<template v-if="q.trim()">
          {{ total === 1 ? "matches" : "match" }} “{{ q.trim() }}”</template
        >.
      </p>
      <table class="recipe-table author-list">
        <thead>
          <tr>
            <th scope="col">Author</th>
            <th scope="col">Known for</th>
            <th scope="col" class="numeric">Sources</th>
            <th scope="col" class="numeric">Recipes</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in authors" :key="a.id">
            <td>
              <a :href="`/authors/${a.id}`" class="strong">{{ a.name }}</a>
              <span v-if="a.kind === 'organisation'" class="badge">Organization</span>
            </td>
            <td :class="{ empty: !a.known_for }">
              <template v-if="a.known_for">
                <span class="cell-label">Known for </span>
                <a :href="`/sources/${a.known_for.id}`">{{ a.known_for.title }}</a>
              </template>
              <span v-else class="muted"
                ><span aria-hidden="true">—</span><span class="visually-hidden">None</span></span
              >
            </td>
            <td class="numeric">
              {{ a.sources.toLocaleString() }}<span class="cell-label">
                {{ a.sources === 1 ? " source" : " sources" }}</span
              >
            </td>
            <td class="numeric">
              {{ a.recipes.toLocaleString() }}<span class="cell-label">
                {{ a.recipes === 1 ? " recipe" : " recipes" }}</span
              >
            </td>
          </tr>
        </tbody>
      </table>
      <p v-if="authors.length < total" class="show-more">
        <button type="button" class="secondary" :disabled="loading" @click="load(true)">
          Show more ({{ (total - authors.length).toLocaleString() }} left)
        </button>
      </p>
    </template>
  </article>
</template>
