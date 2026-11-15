<script setup lang="ts">
import SignInLink from "../components/SignInLink.vue";
import { computed, ref, watch } from "vue";
import SourceCover from "../components/SourceCover.vue";
import type { Me } from "../me";
import {
  myShelf,
  putOnShelf,
  type Shelf,
  type ShelfBook,
  shareShelf,
  takeOffShelf,
} from "../shelf";

// Your shelf (routers/shelf.py): the books you own, then the shelves shared
// with you. SCOPING.md: "mark books you own, filter search to your shelf";
// shared with household groups as a larder list is (Ray, 2026-11-11). Under
// each shelf's books are the ones its owner wants (Ray, 2026-11-14): a
// second state of the shelf, shown apart, since search and the count are
// of the books that are had.
const props = defineProps<{ user: Me | null | undefined }>();
document.title = "Your shelf · OpenLarder";

const shelf = ref<Shelf | null>(null);
const error = ref("");
const busy = ref(false);
const filter = ref("");
const sharing = ref(false);
function matching(books: ShelfBook[]) {
  const words = filter.value.toLowerCase().split(/\s+/).filter(Boolean);
  return books.filter((b) => {
    const text = [b.title, b.subtitle, ...b.authors].join(" ").toLowerCase();
    return words.every((w) => text.includes(w));
  });
}
const had = (books: ShelfBook[]) => books.filter((b) => b.state === "have");
const wanted = (books: ShelfBook[]) => books.filter((b) => b.state === "want");
// Yours, then each shared with you: one layout for both. Each has the
// books had, and under them the ones wanted.
const shelves = computed(() =>
  shelf.value
    ? [
        {
          key: "mine",
          owner: undefined,
          title: "",
          note: "",
          wantsTitle: "Books you want",
          editable: true,
          books: had(shelf.value.books),
          wants: wanted(shelf.value.books),
        },
        ...shelf.value.shared.map((s) => ({
          key: s.owner_id,
          owner: s.owner_id as string | undefined,
          title: `${s.owner_name ?? "Someone"}'s shelf`,
          note: `Shared with you through ${s.through.map((g) => g.name).join(", ")}${
            s.editable ? "" : ": you can see it, not change it"
          }.`,
          wantsTitle: s.owner_name ? `Books ${s.owner_name} wants` : "Books they want",
          editable: s.editable,
          books: had(s.books),
          wants: wanted(s.books),
        })),
      ]
    : [],
);
const every = computed(() => shelves.value.flatMap((s) => [...s.books, ...s.wants]));
// Of the books had: what search with your shelf looks in.
const count = computed(() => new Set(shelves.value.flatMap((s) => s.books).map((b) => b.id)).size);
const wantCount = computed(
  () => new Set(shelves.value.flatMap((s) => s.wants).map((b) => b.id)).size,
);

function editionLabel(b: ShelfBook) {
  return [b.edition_year, b.edition_isbn13 && `ISBN ${b.edition_isbn13}`]
    .filter(Boolean)
    .join(" · ");
}

async function act(work: () => Promise<Shelf | void>) {
  busy.value = true;
  error.value = "";
  try {
    shelf.value = (await work()) ?? (await myShelf());
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

const remove = (b: ShelfBook, owner?: string) => act(() => takeOffShelf(b.id, owner));
// A wanted book that's arrived: it's one had now. Which edition is said on
// its page.
const got = (b: ShelfBook, owner?: string) =>
  act(async () => {
    await putOnShelf(b.id, null, owner);
  });
function toggleGroup(groupId: string, on: boolean) {
  const ids = new Set(shelf.value!.shared_with.map((g) => g.id));
  if (on) ids.add(groupId);
  else ids.delete(groupId);
  act(() => shareShelf([...ids]));
}

watch(
  () => props.user,
  (user) => {
    if (user && !shelf.value) act(async () => {});
  },
  { immediate: true },
);
</script>

<template>
  <article class="wide shelf-page">
    <div class="list-head">
      <h1>Your shelf</h1>
      <p class="muted">
        The cookbooks you own. Search can keep to them, and a recipe's page opens at the page in
        the edition you have. Only you see your shelf, and the household
        <a href="/groups">groups</a> you share it with. To add a book, open its page and choose “I
        have this book”, or “I want this book” for one you don't have yet.
      </p>
    </div>
    <p v-if="user === null" class="status">
      <SignInLink /> to keep a shelf.
    </p>
    <template v-else-if="user">
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="!shelf && !error" class="status">Loading…</p>
      <template v-else-if="shelf">
        <p v-if="count || wantCount" class="status shelf-summary">
          <span
            >{{ count.toLocaleString() }} {{ count === 1 ? "book" : "books"
            }}<template v-if="wantCount">, and {{ wantCount.toLocaleString() }} wanted</template
            >.</span
          >
          <a v-if="count" href="/search?own=1" class="secondary">Search my shelf</a>
        </p>
        <div v-if="every.length > 8" class="list-find">
          <label for="shelf-filter">Find on the shelves</label>
          <input
            id="shelf-filter"
            v-model="filter"
            type="search"
            autocomplete="off"
            placeholder="Title or author"
          />
        </div>
        <section v-for="s in shelves" :key="s.key" class="shelf-section">
          <template v-if="s.owner">
            <h2>{{ s.title }}</h2>
            <p class="muted">{{ s.note }}</p>
          </template>
          <template v-else>
            <p v-if="shelf.groups.length" class="shelf-sharing">
              <span v-if="shelf.shared_with.length && !sharing" class="muted"
                >Shared with {{ shelf.shared_with.map((g) => g.name).join(", ") }}.</span
              >
              <button
                type="button"
                class="secondary small"
                :aria-expanded="sharing"
                @click="sharing = !sharing"
              >
                Share
              </button>
            </p>
            <fieldset v-if="sharing" class="larder-share">
              <legend>Who else sees it</legend>
              <label v-for="g in shelf.groups" :key="g.id" class="check">
                <input
                  type="checkbox"
                  :checked="shelf.shared_with.some((x) => x.id === g.id)"
                  :disabled="busy"
                  @change="toggleGroup(g.id, ($event.target as HTMLInputElement).checked)"
                />
                {{ g.name }}
              </label>
              <p class="help">
                Its members see your shelf; editors and admins of the group change what's on it.
              </p>
            </fieldset>
          </template>
          <p v-if="!s.books.length && !s.wants.length" class="status">
            <template v-if="s.owner">Nothing on it yet.</template>
            <template v-else>
              Nothing on yours yet. Find your books on <a href="/sources">Sources</a>.
            </template>
          </p>
          <p v-else-if="!s.books.length" class="status">
            <template v-if="s.owner">No books yet, only ones wanted.</template>
            <template v-else>No books of your own yet, only ones you want.</template>
          </p>
          <ul v-else class="cover-grid">
            <li v-for="b in matching(s.books)" :key="b.id">
              <a :href="`/sources/${b.id}`" class="cover-card">
                <SourceCover
                  :src="b.cover_url"
                  :title="b.title"
                  :byline="b.authors.join(', ')"
                  :kind="b.kind"
                />
                <strong>{{ b.title }}</strong>
                <span v-if="b.authors.length" class="byline">{{ b.authors.join(", ") }}</span>
                <span v-if="b.editions > 1 && editionLabel(b)" class="byline"
                  >{{ s.owner ? "Theirs" : "Yours" }}: {{ editionLabel(b) }}</span
                >
                <span class="byline"
                  >{{ b.recipes.toLocaleString() }}
                  {{ b.recipes === 1 ? "recipe" : "recipes" }}</span
                >
              </a>
              <button
                v-if="s.editable"
                type="button"
                class="secondary small shelf-remove"
                :disabled="busy"
                :aria-label="`Take off ${b.title}`"
                @click="remove(b, s.owner)"
              >
                Take off
              </button>
            </li>
          </ul>
          <p v-if="s.books.length && !matching(s.books).length" class="status">
            Nothing here matches “{{ filter }}”.
          </p>
          <!-- The books wanted, apart: they aren't in a search of the shelf
               or in its count. -->
          <template v-if="s.wants.length">
            <component :is="s.owner ? 'h3' : 'h2'" class="shelf-wants">{{ s.wantsTitle }}</component>
            <ul class="cover-grid">
              <li v-for="b in matching(s.wants)" :key="b.id">
                <a :href="`/sources/${b.id}`" class="cover-card">
                  <SourceCover
                    :src="b.cover_url"
                    :title="b.title"
                    :byline="b.authors.join(', ')"
                    :kind="b.kind"
                  />
                  <strong>{{ b.title }}</strong>
                  <span v-if="b.authors.length" class="byline">{{ b.authors.join(", ") }}</span>
                  <span class="byline"
                    >{{ b.recipes.toLocaleString() }}
                    {{ b.recipes === 1 ? "recipe" : "recipes" }}</span
                  >
                </a>
                <div v-if="s.editable" class="shelf-want-actions">
                  <button
                    type="button"
                    class="secondary small"
                    :disabled="busy"
                    :aria-label="`${s.owner ? 'They have it now' : 'I have it now'}: ${b.title}`"
                    @click="got(b, s.owner)"
                  >
                    {{ s.owner ? "They have it now" : "I have it now" }}
                  </button>
                  <button
                    type="button"
                    class="secondary small"
                    :disabled="busy"
                    :aria-label="`Take off ${b.title}`"
                    @click="remove(b, s.owner)"
                  >
                    Take off
                  </button>
                </div>
              </li>
            </ul>
            <p v-if="!matching(s.wants).length" class="status">
              Nothing wanted matches “{{ filter }}”.
            </p>
          </template>
        </section>
      </template>
    </template>
  </article>
</template>

<style scoped>
.shelf-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}
.shelf-section + .shelf-section {
  margin-top: 2rem;
}
.shelf-sharing {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.75rem;
  margin: 0 0 0.75rem;
}
.shelf-remove {
  margin-top: 0.25rem;
}
.shelf-wants {
  margin: 1.5rem 0 0.75rem;
  font-size: 1.125rem;
}
.shelf-want-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.375rem;
  margin-top: 0.25rem;
}
</style>
