<script setup lang="ts">
import { onMounted, ref } from "vue";
import { addLink, type Author, fetchAuthor, removeLink, saveAuthor } from "../authors";
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

const add = () =>
  act(async () => {
    const link = await addLink(props.id, linkUrl.value, linkLabel.value);
    author.value!.links.push(link);
    linkUrl.value = "";
    linkLabel.value = "";
  });

const remove = (link: Author["links"][number]) =>
  act(async () => {
    if (!confirm(`Remove the link to ${link.label ?? link.url}?`)) return;
    await removeLink(props.id, link.id);
    author.value!.links = author.value!.links.filter((x) => x.id !== link.id);
  });

// "photographer", or "author and photographer"; plain authorship goes unsaid.
function roles(list: string[]) {
  return list.length === 1 && list[0] === "author" ? "" : list.join(" and ");
}

onMounted(load);
</script>

<template>
  <article>
    <p><a href="/authors">← All authors</a></p>
    <p v-if="missing">There's no author here. The link may be wrong.</p>
    <p v-else-if="failed" role="alert">This author couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="!author" class="status">Loading…</p>
    <template v-else>
      <h1>{{ author.name }}</h1>
      <ul v-if="author.links.length || author.open_library_url" class="author-links">
        <li v-for="link in author.links" :key="link.id">
          <a :href="link.url" rel="nofollow noopener">{{ link.label ?? link.url }}</a>
          <button
            v-if="user?.is_admin"
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
          <a :href="author.open_library_url">On Open Library</a>
        </li>
      </ul>

      <h2>Books</h2>
      <ul class="book-list">
        <li v-for="b in author.sources" :key="b.id">
          <a :href="`/sources/${b.id}`" class="book-card">
            <img v-if="b.cover_url" :src="b.cover_url" alt="" loading="lazy" />
            <span v-else class="no-cover" aria-hidden="true"></span>
            <span>
              <strong>{{ b.title }}</strong>
              <span v-if="roles(b.roles)" class="byline">{{ roles(b.roles) }}</span>
              <span v-if="b.credited_as !== author.name" class="byline"
                >as {{ b.credited_as }}</span
              >
            </span>
          </a>
        </li>
      </ul>

      <template v-if="author.coauthors.length">
        <h2>Worked with</h2>
        <ul class="recipe-list">
          <li v-for="c in author.coauthors" :key="c.id">
            <a :href="`/authors/${c.id}`">{{ c.name }}</a>
            <span class="page-ref">
              {{ c.sources }} {{ c.sources === 1 ? "book" : "books" }} together
            </span>
          </li>
        </ul>
      </template>

      <section v-if="user?.is_admin" class="fix-ingredient">
        <h2>Fix this author</h2>
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
      </section>
    </template>
  </article>
</template>
