<script setup lang="ts">
import CoverBlank from "../components/CoverBlank.vue";
import { computed, onMounted, ref, watch } from "vue";
import AdminBar from "../components/AdminBar.vue";
import AgreementPanel from "../components/AgreementPanel.vue";
import {
  addByIsbn,
  addManually,
  addFamily,
  addPeriodical,
  addNamed,
  addShow,
  addWebsite,
  type BookSummary,
  KIND_NAMES,
  kindPlural,
  listSources,
} from "../books";
import type { Me } from "../me";

defineProps<{ user: Me | null | undefined }>();
document.title = "Sources · OpenLarder";

const books = ref<BookSummary[] | null>(null);
const total = ref(0);
const failed = ref(false);
const loading = ref(false);
const isbn = ref("");
const adding = ref(false);
const error = ref("");

// A page of sources at a time, narrowed on the server as someone types (by
// title, subtitle, author or a website's address): the whole catalog is too
// much for one answer.
const params = new URLSearchParams(location.search);
const filter = ref(params.get("q") ?? "");
// Which kinds to show (all when none), and in what order.
const kinds = ref<string[]>(params.getAll("kind").filter((k) => k in KIND_NAMES));
const sort = ref<"title" | "recipes" | "recent">(
  (["recipes", "recent"] as const).find((s) => s === params.get("sort")) ?? "title",
);
// How many of each kind match the words.
const kindCounts = ref<Record<string, number>>({});
const anyKind = computed(() => Object.values(kindCounts.value).reduce((a, b) => a + b, 0));
// Answers can arrive out of order as someone types; only the latest counts.
let asked = 0;

async function load(more = false) {
  const mine = ++asked;
  loading.value = true;
  failed.value = false;
  try {
    const page = await listSources(
      filter.value,
      more ? (books.value?.length ?? 0) : 0,
      undefined,
      sort.value === "title" ? undefined : sort.value,
      kinds.value,
    );
    if (mine !== asked) return;
    books.value = more ? [...(books.value ?? []), ...page.sources] : page.sources;
    total.value = page.total;
    kindCounts.value = page.kinds;
  } catch {
    if (mine === asked) failed.value = true;
  } finally {
    if (mine === asked) loading.value = false;
  }
}

// The address keeps what's chosen, so a filtered list can be shared.
function remember() {
  const url = new URL(location.href);
  url.searchParams.delete("q");
  url.searchParams.delete("kind");
  url.searchParams.delete("sort");
  if (filter.value.trim()) url.searchParams.set("q", filter.value.trim());
  for (const kind of kinds.value) url.searchParams.append("kind", kind);
  if (sort.value !== "title") url.searchParams.set("sort", sort.value);
  history.replaceState(null, "", url);
}

let timer: ReturnType<typeof setTimeout> | undefined;
watch(filter, () => {
  clearTimeout(timer);
  timer = setTimeout(() => {
    remember();
    load();
  }, 200);
});
watch([kinds, sort], () => {
  remember();
  load();
});
onMounted(() => load());

function toggleKind(kind: string) {
  kinds.value = kinds.value.includes(kind)
    ? kinds.value.filter((k) => k !== kind)
    : [...kinds.value, kind];
}
// The kinds there are, most first, and any chosen that has none now.
const kindChoices = computed(() => {
  const found = Object.entries(kindCounts.value).sort((a, b) => b[1] - a[1]);
  for (const kind of kinds.value) if (!(kind in kindCounts.value)) found.push([kind, 0]);
  return found;
});
const capitalised = (kind: string) => {
  const name = KIND_NAMES[kind] ?? "source";
  return name[0].toUpperCase() + name.slice(1);
};

// A family collection: anyone signed in adds one, private unless an admin
// makes it public; the tick box is required.
const familyName = ref("");
const familyPublic = ref(false);
const familyPrivate = computed(() => !familyPublic.value);
const familyAcknowledged = ref(false);
const familyError = ref("");
async function addCollection() {
  familyError.value = "";
  try {
    const { id } = await addFamily(familyName.value, familyPrivate.value, familyAcknowledged.value);
    location.href = `/sources/${id}`;
  } catch (e) {
    familyError.value = e instanceof Error ? e.message : String(e);
  }
}

// Adding a source other than a book by ISBN: a website (any address on it
// finds the site), or a magazine, newspaper, TV show, podcast, video
// channel, social media account or product by name.
type OtherKind =
  | "website"
  | "magazine"
  | "newspaper"
  | "tv_show"
  | "podcast"
  | "video_channel"
  | "social"
  | "packaging";
const siteKind = ref<OtherKind>("website");
const NAME_EXAMPLES: Record<OtherKind, string> = {
  website: "Smitten Kitchen",
  magazine: "Bon Appétit",
  newspaper: "The New York Times",
  tv_show: "Salt Fat Acid Heat",
  podcast: "The Sporkful",
  video_channel: "Binging with Babish",
  social: "Half Baked Harvest (Instagram)",
  packaging: "Quaker Old Fashioned Oats",
};
// Who a source is by, as the form asks it.
const WHO: Partial<Record<OtherKind, string>> = {
  tv_show: "Who hosts it",
  podcast: "Who hosts it",
  video_channel: "Who hosts it",
  social: "Whose account it is",
  packaging: "Who makes it",
};
const siteAddress = ref("");
const siteName = ref("");
const sitePaywalled = ref(false);
// Who writes it: names separated by commas.
const siteAuthors = ref("");
const siteError = ref("");
async function addSite() {
  siteError.value = "";
  try {
    const authors = siteAuthors.value.split(",").map((a) => a.trim()).filter(Boolean);
    const { id } =
      siteKind.value === "website"
        ? await addWebsite(siteAddress.value, siteName.value, sitePaywalled.value, authors)
        : siteKind.value === "magazine" || siteKind.value === "newspaper"
          ? await addPeriodical(siteKind.value, siteName.value, authors)
          : siteKind.value === "social" || siteKind.value === "packaging"
            ? await addNamed(siteKind.value, siteName.value, authors)
            : await addShow(siteKind.value, siteName.value, authors);
    location.href = `/sources/${id}`;
  } catch (e) {
    siteError.value = e instanceof Error ? e.message : String(e);
  }
}

// A book without an ISBN Open Library knows.
const handTitle = ref("");
const handAuthors = ref("");
const handYear = ref("");
const handIsbn = ref("");
const handError = ref("");
async function addByHand() {
  handError.value = "";
  try {
    const authors = handAuthors.value.split(",").map((a) => a.trim()).filter(Boolean);
    const year = handYear.value.trim() ? Number(handYear.value) : null;
    const { id } = await addManually(handTitle.value, authors, year, handIsbn.value);
    location.href = `/sources/${id}`;
  } catch (e) {
    handError.value = e instanceof Error ? e.message : String(e);
  }
}

const reload = () => location.reload();

async function add() {
  adding.value = true;
  error.value = "";
  try {
    const { id } = await addByIsbn(isbn.value);
    // A full load, so the new book's page fetches what was just stored.
    location.href = `/sources/${id}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
    adding.value = false;
  }
}
</script>

<template>
  <AdminBar v-if="user?.may_edit" :user="user" />
  <article class="wide sources-page">
    <div class="list-head">
      <div>
        <h1>Sources</h1>
        <p class="muted">
          Cookbooks, websites, magazines, shows and more, with the recipes indexed from them.
          <a href="/authors">Browse by author</a>
        </p>
      </div>
    </div>

    <div v-if="user" class="add-panels">
      <!-- Contributors add books, which wait for review; the agreement first. -->
      <AgreementPanel v-if="user.may_claim && !user.agreed" :agreed="false" @accepted="reload" />
      <p v-if="user.may_claim && !user.may_edit && !user.trusted && user.agreed" class="muted add-note">
        Books you add wait for a moderator's review before anyone else sees them.
      </p>
      <details v-if="user.may_claim && user.agreed" class="add-panel">
        <summary>Add a book by ISBN</summary>
        <form class="isbn-form" @submit.prevent="add">
          <label for="isbn">ISBN</label>
          <div class="row">
            <input
              id="isbn"
              v-model="isbn"
              inputmode="numeric"
              autocomplete="off"
              placeholder="978-0-393-54111-3"
              required
              :aria-invalid="error ? 'true' : undefined"
              aria-describedby="isbn-error"
            />
            <button type="submit" class="primary" :disabled="adding">
              {{ adding ? "Looking it up…" : "Add" }}
            </button>
          </div>
          <p v-if="error" id="isbn-error" class="error" role="alert">{{ error }}</p>
        </form>
      </details>
      <details v-if="user.may_claim && user.agreed" class="add-panel">
        <summary>Add a book without an ISBN</summary>
        <form class="recipe-form" @submit.prevent="addByHand">
          <label for="hand-title">Title</label>
          <input id="hand-title" v-model="handTitle" required maxlength="300" />
          <label for="hand-authors">Authors (optional; separate names with commas)</label>
          <input id="hand-authors" v-model="handAuthors" maxlength="500" />
          <label for="hand-year">Year (optional)</label>
          <input id="hand-year" v-model="handYear" inputmode="numeric" maxlength="4" />
          <label for="hand-isbn">ISBN, if it has one Open Library doesn't know (optional)</label>
          <input id="hand-isbn" v-model="handIsbn" inputmode="numeric" maxlength="40" />
          <p v-if="handError" class="error" role="alert">{{ handError }}</p>
          <button type="submit" class="primary">Add the book</button>
        </form>
      </details>
      <details v-if="user.may_edit && user.agreed" class="add-panel">
        <summary>Add another kind of source</summary>
        <form class="recipe-form site-form" @submit.prevent="addSite">
          <label for="site-kind">What it is</label>
          <select id="site-kind" v-model="siteKind">
            <option value="website">A website</option>
            <option value="magazine">A magazine</option>
            <option value="newspaper">A newspaper</option>
            <option value="tv_show">A TV show</option>
            <option value="podcast">A podcast</option>
            <option value="video_channel">A video channel</option>
            <option value="social">A social media account</option>
            <option value="packaging">A product's packaging</option>
          </select>
          <template v-if="siteKind === 'website'">
            <label for="site-address">Any page on it</label>
            <input
              id="site-address"
              v-model="siteAddress"
              required
              autocomplete="off"
              placeholder="https://smittenkitchen.com"
            />
            <label for="site-name">What it calls itself (optional)</label>
            <input id="site-name" v-model="siteName" maxlength="300" placeholder="Smitten Kitchen" />
          </template>
          <template v-else>
            <label for="site-name">Its name</label>
            <input
              id="site-name"
              v-model="siteName"
              required
              maxlength="300"
              :placeholder="NAME_EXAMPLES[siteKind]"
            />
          </template>
          <label for="site-authors"
            >{{ WHO[siteKind] ?? "Who writes it" }} (optional; separate names with
            commas)</label
          >
          <input id="site-authors" v-model="siteAuthors" maxlength="500" placeholder="Deb Perelman" />
          <label v-if="siteKind === 'website'" class="check"
            ><input v-model="sitePaywalled" type="checkbox" /> Behind a subscription</label
          >
          <p v-if="siteError" class="error" role="alert">{{ siteError }}</p>
          <button type="submit" class="primary">Add the {{ KIND_NAMES[siteKind] }}</button>
        </form>
      </details>
      <details class="add-panel">
        <summary>Add a family collection</summary>
        <form class="recipe-form family-form" @submit.prevent="addCollection">
          <label for="family-name">Its name</label>
          <input
            id="family-name"
            v-model="familyName"
            required
            maxlength="300"
            placeholder="Grandma's recipe box"
          />
          <p class="help">
            A recipe box, a church or school cookbook, a class's handouts: recipes your family keeps.
          </p>
          <div class="notice">
            <p>
              <strong>What OpenLarder keeps:</strong> the collection's name, each recipe's title and
              the names of its ingredients. Never amounts or the method.
            </p>
            <p v-if="familyPrivate">
              <strong>Who sees it:</strong> only you. It isn't listed, searched or counted for anyone
              else, admins included. The people who run the site can reach anything stored on it, as
              on any website.
            </p>
            <p v-else>
              <strong>Who sees it:</strong> everyone. It becomes part of OpenLarder's open data,
              which anyone may copy under the ODbL.
            </p>
          </div>
          <label v-if="user.may_edit" class="check"
            ><input v-model="familyPublic" type="checkbox" /> Public, for everyone</label
          >
          <label class="check"
            ><input v-model="familyAcknowledged" type="checkbox" required /> I understand what
            OpenLarder keeps and who sees it</label
          >
          <p v-if="familyError" class="error" role="alert">{{ familyError }}</p>
          <button type="submit" class="primary">Add the collection</button>
        </form>
      </details>
    </div>

    <div class="list-tools">
      <div class="list-find">
        <label for="book-filter">Find a source</label>
        <input
          id="book-filter"
          v-model="filter"
          type="search"
          autocomplete="off"
          placeholder="Title, author or website"
        />
        <!-- Requests is in the footer; this is where someone wants it. -->
        <p class="help request-prompt">
          Can't find a source? <a href="/requests">Request it</a>
        </p>
      </div>
      <div class="table-controls">
        <label for="source-sort">Sort</label>
        <select id="source-sort" v-model="sort">
          <option value="title">Title</option>
          <option value="recipes">Most recipes</option>
          <option value="recent">Newest added</option>
        </select>
      </div>
    </div>
    <div v-if="kindChoices.length > 1 || kinds.length" class="kind-filter" role="group" aria-label="Kinds">
      <button type="button" class="secondary small" :aria-pressed="!kinds.length" @click="kinds = []">
        All <span class="count">{{ anyKind.toLocaleString() }}</span>
      </button>
      <button
        v-for="[kind, count] in kindChoices"
        :key="kind"
        type="button"
        class="secondary small"
        :aria-pressed="kinds.includes(kind)"
        @click="toggleKind(kind)"
      >
        {{ kindPlural(kind) }} <span class="count">{{ count.toLocaleString() }}</span>
      </button>
    </div>

    <p v-if="failed" role="alert">The sources couldn't be loaded. Try reloading the page.</p>
    <p v-else-if="books === null" class="status">Loading…</p>
    <p v-else-if="total === 0 && !filter.trim() && !kinds.length">No sources yet.</p>
    <p v-else class="status results-count" role="status">
      {{ total.toLocaleString() }} {{ total === 1 ? "source" : "sources" }}<template
        v-if="filter.trim()"
      >
        {{ total === 1 ? "matches" : "match" }} “{{ filter.trim() }}”</template
      >.
      <a v-if="total === 0 && filter.trim()" :href="`/search?q=${encodeURIComponent(filter.trim())}`"
        >Look for recipes with “{{ filter.trim() }}” in the title instead</a
      >
    </p>
    <ul v-if="books?.length" class="cover-grid">
      <li v-for="book in books" :key="book.id">
        <a :href="`/sources/${book.id}`" class="cover-card">
          <img v-if="book.cover_url" :src="book.cover_url" alt="" loading="lazy" />
          <CoverBlank
            v-else
            :title="book.title"
            :byline="book.authors.join(', ') || book.host"
            :kind="book.kind"
          />
          <span class="kind">{{ KIND_NAMES[book.kind] ?? "source" }}</span>
          <strong>{{ book.title }}</strong>
          <span v-if="book.authors.length" class="byline">{{ book.authors.join(", ") }}</span>
          <span v-else-if="book.host" class="byline">{{ book.host }}</span>
          <span class="byline"
            >{{ book.recipes.toLocaleString() }} {{ book.recipes === 1 ? "recipe" : "recipes"
            }}<template v-if="book.private"> · private</template></span
          >
        </a>
      </li>
    </ul>
    <p v-if="books && books.length < total" class="show-more">
      <button type="button" class="secondary" :disabled="loading" @click="load(true)">
        Show more ({{ (total - books.length).toLocaleString() }} left)
      </button>
    </p>
  </article>
</template>
