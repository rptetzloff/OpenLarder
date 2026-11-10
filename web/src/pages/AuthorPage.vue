<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  addLink,
  type Author,
  type AuthorSummary,
  fetchAuthor,
  lifespan,
  listAuthors,
  mergeAuthor,
  removeLink,
  saveAuthor,
  setWikidata,
} from "../authors";
import { KIND_NAMES } from "../books";
import type { Me } from "../me";

const props = defineProps<{ id: string; user: Me | null | undefined }>();
const author = ref<Author | null>(null);
const missing = ref(false);
const failed = ref(false);

// Fixing it, for admins.
const name = ref("");
const kind = ref<Author["kind"]>("person");
const linkUrl = ref("");
const linkLabel = ref("");
const error = ref("");
const busy = ref(false);

async function load() {
  try {
    const found = await fetchAuthor(props.id);
    if (found === null) missing.value = true;
    else {
      author.value = found;
      name.value = found.name;
      kind.value = found.kind;
      wikidataRef.value = found.wikidata_url?.split("/").pop() ?? "";
      document.title = `${found.name} · OpenLarder`;
    }
  } catch {
    failed.value = true;
  }
}

async function act(work: () => Promise<unknown>) {
  error.value = "";
  busy.value = true;
  try {
    await work();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

const save = () =>
  act(async () => {
    await saveAuthor(props.id, name.value, kind.value);
    await load();
  });

// Which Wikidata item the author is, for admins; its facts come with it.
const wikidataRef = ref("");
const saveWikidata = (reference: string | null) =>
  act(async () => {
    author.value = await setWikidata(props.id, reference);
    wikidataRef.value = author.value.wikidata_url?.split("/").pop() ?? "";
  });

// The facts line: years, country, and the website unless it's a link
// already.
const facts = computed(() => {
  const a = author.value;
  if (!a) return [];
  return [lifespan(a), a.country ?? ""].filter(Boolean);
});
const website = computed(() => {
  const a = author.value;
  return a?.website && !a.links.some((l) => l.url === a.website) ? a.website : null;
});

const add = () =>
  act(async () => {
    const link = await addLink(props.id, linkUrl.value, linkLabel.value);
    author.value!.links.push(link);
    linkUrl.value = "";
    linkLabel.value = "";
  });

// Merging: another record of this person into this one, or this one into
// another found by typing.
async function merge(gone: AuthorSummary | Author, kept: AuthorSummary | Author) {
  const message =
    `Merge “${gone.name}” into “${kept.name}”?

` +
    `Everything credited to “${gone.name}” will be credited to “${kept.name}”. ` +
    "Each book or site still prints the name it prints.";
  if (!confirm(message)) return;
  await act(async () => {
    await mergeAuthor(gone.id, kept.id);
    if (kept.id === props.id) await load();
    else location.href = `/authors/${kept.id}`;
  });
}

const mergeQuery = ref("");
const candidates = ref<AuthorSummary[]>([]);
let asked = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
watch(mergeQuery, () => {
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const mine = ++asked;
    const q = mergeQuery.value.trim();
    const found = q ? (await listAuthors(q).catch(() => null))?.authors : [];
    if (mine === asked && found) candidates.value = found.filter((a) => a.id !== props.id).slice(0, 8);
  }, 200);
});

const remove = (link: Author["links"][number]) =>
  act(async () => {
    if (!confirm(`Remove the link to ${link.label ?? link.url}?`)) return;
    await removeLink(props.id, link.id);
    author.value!.links = author.value!.links.filter((x) => x.id !== link.id);
  });

// "Books", "Magazines", "TV shows", by what they've made; "Sources" for a mix.
const sourcesHeading = computed(() => {
  const kinds = [...new Set(author.value?.sources.map((s) => s.kind))];
  if (kinds.length > 1) return "Sources";
  const name = KIND_NAMES[kinds[0] ?? "book"] ?? "book";
  return `${name[0].toUpperCase()}${name.slice(1)}s`;
});

// "photographer", or "author and photographer"; plain authorship goes unsaid.
function roles(list: string[]) {
  return list.length === 1 && list[0] === "author" ? "" : list.join(" and ");
}

onMounted(load);
</script>

<template>
  <article class="wide author-page">
    <p v-if="missing">There's no author here. The link may be wrong.</p>
    <p v-else-if="failed" role="alert">This author couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!author" class="status">Loading…</p>
    <template v-else>
      <Teleport v-if="user?.may_edit" to="#admin-bar" defer>
        <div class="admin-bar">
          <div class="bar">
            <strong>Admin</strong>
            <a href="#author-name">Edit name and kind</a>
            <a href="#link-url">Edit links</a>
            <a href="#wikidata-item">Wikidata</a>
            <template v-if="author.same_name.length">
              <span>
                Possible duplicate:
                <a :href="`/authors/${author.same_name[0].id}`">{{ author.same_name[0].name }}</a>
                ·
                <a href="#same-name">Merge</a>
              </span>
            </template>
          </div>
        </div>
      </Teleport>

      <nav class="crumbs" aria-label="Breadcrumb">
        <a href="/authors">Authors</a>
        <span aria-hidden="true">/</span>
        <span aria-current="page">{{ author.name }}</span>
      </nav>

      <div class="author-head">
        <p class="kind">{{ author.kind === "organisation" ? "Organisation" : "Person" }}</p>
        <h1>{{ author.name }}</h1>
        <p v-if="facts.length" class="author-facts">{{ facts.join(" · ") }}</p>
        <ul
          v-if="author.links.length || author.open_library_url || author.wikidata_url"
          class="author-links"
        >
          <li v-if="website">
            <a :href="website" rel="nofollow noopener">Website</a>
          </li>
          <li v-for="link in author.links" :key="link.id">
            <a :href="link.url" rel="nofollow noopener">{{ link.label ?? link.url }}</a>
            <button
              v-if="user?.may_edit"
              type="button"
              class="link remove-alias"
              :disabled="busy"
              :aria-label="`Remove the link to ${link.label ?? link.url}`"
              @click="remove(link)"
            >
              ×
            </button>
          </li>
          <li v-if="author.open_library_url">
            <a :href="author.open_library_url">Open Library</a>
          </li>
          <li v-if="author.wikidata_url">
            <a :href="author.wikidata_url">Wikidata</a>
          </li>
        </ul>
      </div>

      <section class="source-section">
        <h2>{{ sourcesHeading }}</h2>
        <ul class="cover-grid">
          <li v-for="b in author.sources" :key="b.id">
            <a :href="`/sources/${b.id}`" class="cover-card">
              <img v-if="b.cover_url" :src="b.cover_url" alt="" loading="lazy" />
              <span v-else class="cover-blank" aria-hidden="true"></span>
              <strong>{{ b.title }}</strong>
              <span class="byline">
                {{ b.recipes.toLocaleString() }} {{ b.recipes === 1 ? "recipe" : "recipes"
                }}{{ roles(b.roles) ? ` · ${roles(b.roles)}` : "" }}
              </span>
              <span v-if="b.credited_as !== author.name" class="byline"
                >printed as “{{ b.credited_as }}”</span
              >
            </a>
          </li>
        </ul>
      </section>

      <section v-if="author.coauthors.length" class="source-section">
        <h2>Credited with</h2>
        <ul class="ingredient-chips">
          <li v-for="c in author.coauthors" :key="c.id">
            <a :href="`/authors/${c.id}`">{{ c.name }}</a>
            <span class="count"> · {{ c.sources }} {{ c.sources === 1 ? "source" : "sources" }}</span>
          </li>
        </ul>
      </section>

      <section v-if="user?.may_edit" class="fix-ingredient source-section">
        <h2>Fix this author</h2>
        <template v-if="author.same_name.length">
          <h3 id="same-name">Possibly the same person</h3>
          <ul class="recipe-list">
            <li v-for="a in author.same_name" :key="a.id">
              <a :href="`/authors/${a.id}`">{{ a.name }}</a>
              <span class="page-ref">{{ a.sources }} {{ a.sources === 1 ? "source" : "sources" }}</span>
              <button type="button" class="link merge-here" :disabled="busy" @click="merge(a, author)">
                Merge into this one
              </button>
            </li>
          </ul>
        </template>
        <p class="status">
          The author's own name, wherever it's shown for them. To change how one book prints it,
          edit the book.
        </p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <form class="recipe-form" @submit.prevent="save">
          <label for="author-name">Name</label>
          <input id="author-name" v-model="name" required maxlength="200" />
          <label for="author-kind">A person or an organisation</label>
          <select id="author-kind" v-model="kind">
            <option value="person">Person</option>
            <option value="organisation">Organisation</option>
          </select>
          <button type="submit" class="primary" :disabled="busy">Save</button>
        </form>
        <form class="recipe-form author-link-form" @submit.prevent="add">
          <label for="link-url">Add a link: their website or an account</label>
          <input
            id="link-url"
            v-model="linkUrl"
            type="url"
            required
            maxlength="500"
            placeholder="https://ottolenghi.co.uk"
          />
          <label for="link-label">Label (optional)</label>
          <input id="link-label" v-model="linkLabel" maxlength="100" placeholder="Website" />
          <button type="submit" class="primary" :disabled="busy">Add the link</button>
        </form>
        <form class="recipe-form author-wikidata" @submit.prevent="saveWikidata(wikidataRef)">
          <label for="wikidata-item">Wikidata item</label>
          <input
            id="wikidata-item"
            v-model="wikidataRef"
            autocomplete="off"
            maxlength="300"
            placeholder="Q214477, or a link to the item"
            aria-describedby="wikidata-help"
          />
          <p id="wikidata-help" class="help">
            Born and died, country and website come from it. An author with an Open Library
            record is usually found by that, from the Admin page.
          </p>
          <div class="row-actions">
            <button type="submit" class="primary" :disabled="busy || !wikidataRef.trim()">
              Use this item
            </button>
            <button
              v-if="author.wikidata_url"
              type="button"
              class="secondary small"
              :disabled="busy"
              @click="saveWikidata(null)"
            >
              Take it off
            </button>
          </div>
        </form>
        <div class="isbn-form author-merge">
          <label for="merge-author">Merge this author into another</label>
          <div class="row">
            <input
              id="merge-author"
              v-model="mergeQuery"
              type="search"
              autocomplete="off"
              placeholder="the one to keep"
            />
          </div>
          <ul v-if="candidates.length" class="merge-candidates">
            <li v-for="c in candidates" :key="c.id">
              <button type="button" class="link" :disabled="busy" @click="merge(author, c)">
                {{ c.name }}
              </button>
              <span class="page-ref">{{ c.sources }} {{ c.sources === 1 ? "source" : "sources" }}</span>
            </li>
          </ul>
        </div>
      </section>
    </template>
  </article>
</template>
