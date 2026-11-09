<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import NameForm from "./components/NameForm.vue";
import { takeRememberedInvite } from "./groups";
import { chooseTheme, savedTheme, type ThemeChoice } from "./theme";
import type { Me } from "./me";
import AccountPage from "./pages/AccountPage.vue";
import AdminImportPage from "./pages/AdminImportPage.vue";
import AdminImportsPage from "./pages/AdminImportsPage.vue";
import AdminPage from "./pages/AdminPage.vue";
import AuthorPage from "./pages/AuthorPage.vue";
import AuthorsPage from "./pages/AuthorsPage.vue";
import FlagsPage from "./pages/FlagsPage.vue";
import HomePage from "./pages/HomePage.vue";
import GroupPage from "./pages/GroupPage.vue";
import GroupsPage from "./pages/GroupsPage.vue";
import InvitePage from "./pages/InvitePage.vue";
import IngredientPage from "./pages/IngredientPage.vue";
import IngredientsPage from "./pages/IngredientsPage.vue";
import BookEditPage from "./pages/BookEditPage.vue";
import BookPage from "./pages/BookPage.vue";
import BooksPage from "./pages/BooksPage.vue";
import RecipeFormPage from "./pages/RecipeFormPage.vue";
import RecipePage from "./pages/RecipePage.vue";
import SearchPage from "./pages/SearchPage.vue";
import PrivacyPage from "./pages/PrivacyPage.vue";
import TermsPage from "./pages/TermsPage.vue";

// The server returns this app for any path it has no file for, so the page
// is chosen from the address. A handful of pages, one with an ID in it,
// still don't need a router library; that changes when pages need nested
// routes or navigation without a full load.
const pages: Record<string, unknown> = { "/privacy": PrivacyPage, "/terms": TermsPage };
// Books became sources (migration 0019): an old /books address, saved or
// shared, goes to the same page under /sources.
if (/^\/books(\/|$)/.test(location.pathname)) {
  location.replace(location.pathname.replace(/^\/books/, "/sources") + location.search);
}
const path = location.pathname.replace(/\/+$/, "");
const page = pages[path];
const onAccount = path === "/account";
const onBooks = path === "/sources";
const onIngredients = path === "/ingredients";
const onSearch = path === "/search";
const onAuthors = path === "/authors";
const onAdmin = path === "/admin";
const onGroups = path === "/groups";
const onImport = path === "/admin/import";
const onImports = path === "/admin/imports";
const flagScope = ({ "/admin/flags": "all", "/account/flags": "mine" } as const)[path];
const UUID = "([0-9a-f-]{36})";
const match = (pattern: string) => path.match(new RegExp(`^${pattern}$`, "i"))?.[1] ?? null;
const bookId = match(`/sources/${UUID}`);
const newRecipeFor = match(`/sources/${UUID}/recipes/new`);
const editBookId = match(`/sources/${UUID}/edit`);
const recipeId = match(`/recipes/${UUID}`);
const ingredientId = match(`/ingredients/${UUID}`);
const authorId = match(`/authors/${UUID}`);
const editRecipeId = match(`/recipes/${UUID}/edit`);
const groupId = match(`/groups/${UUID}`);
// An invite link's token (secrets.token_urlsafe).
const inviteCode = match("/invite/([A-Za-z0-9_-]+)");

const theme = ref<ThemeChoice>(savedTheme());

// The main sections, so the header can mark the one you're in.
const SECTIONS = [
  { href: "/search", label: "Search" },
  { href: "/sources", label: "Sources" },
  { href: "/ingredients", label: "Ingredients" },
  { href: "/authors", label: "Authors" },
];
const inSection = (href: string) => path === href || path.startsWith(`${href}/`);
// undefined while asking, null when signed out.
const user = ref<Me | null | undefined>(undefined);
// Someone signed in who hasn't chosen a name yet is asked for one before
// anything else, except the privacy and terms pages, which stay readable.
const needsName = computed(() => !!user.value && !user.value.display_name && !page);
// The callback says only that sign-in failed, never why; the reason is in
// the server log, out of reach of whoever might be forging the request.
const signInFailed = new URLSearchParams(location.search).get("sign-in") === "failed";

onMounted(async () => {
  try {
    const res = await fetch("/api/auth/me");
    user.value = res.ok ? await res.json() : null;
  } catch {
    user.value = null;
  }
  // Back to an invite that sent them to sign in.
  const pending = user.value ? takeRememberedInvite() : null;
  if (pending && !inviteCode) location.replace(`/invite/${pending}`);
});
</script>

<template>
  <header class="site-header">
    <div class="bar">
      <a href="/" class="brand">
        <!-- The full logo, in the version for the page's light or dark; CSS
             shows the one that matches data-theme. -->
        <img class="for-light" src="/logo-light.svg" alt="OpenLarder" width="140" height="36" />
        <img class="for-dark" src="/logo-dark.svg" alt="OpenLarder" width="140" height="36" />
      </a>
      <nav class="primary-nav" aria-label="Main">
        <a
          v-for="s in SECTIONS"
          :key="s.href"
          :href="s.href"
          :aria-current="inSection(s.href) ? 'page' : undefined"
          >{{ s.label }}</a
        >
      </nav>
      <div class="account">
        <template v-if="user">
          <a v-if="user.is_admin" href="/admin">Admin</a>
          <a href="/groups">Groups</a>
          <a href="/account">{{ user.display_name ?? "Choose a name" }}</a>
          <!-- A form, not fetch: signing out ends at the broker, which ends the
               session there and sends the browser back here. -->
          <form method="post" action="/api/auth/logout">
            <button type="submit">Sign out</button>
          </form>
        </template>
        <!-- A full page load, not fetch: the broker's sign-in page is a redirect. -->
        <a v-else-if="user === null" href="/api/auth/login" class="button-outline">Sign in</a>
      </div>
    </div>
  </header>
  <main>
    <component :is="page" v-if="page" />
    <section v-else-if="needsName && user">
      <h1>What should we call you?</h1>
      <p>Pick the name OpenLarder shows for you. You can change it later on your account page.</p>
      <NameForm
        :initial="user.suggested_name ?? ''"
        submit-label="Continue"
        @saved="(me) => (user = me)"
      />
    </section>
    <AccountPage v-else-if="onAccount" :user="user" @saved="(me) => (user = me)" />
    <BooksPage v-else-if="onBooks" :user="user" />
    <IngredientsPage v-else-if="onIngredients" />
    <SearchPage v-else-if="onSearch" />
    <AuthorsPage v-else-if="onAuthors" />
    <AuthorPage v-else-if="authorId" :id="authorId" :user="user" />
    <IngredientPage v-else-if="ingredientId" :id="ingredientId" :user="user" />
    <AdminPage v-else-if="onAdmin" :user="user" />
    <GroupsPage v-else-if="onGroups" :user="user" />
    <GroupPage v-else-if="groupId" :id="groupId" :user="user" />
    <InvitePage v-else-if="inviteCode" :code="inviteCode" :user="user" />
    <AdminImportPage v-else-if="onImport" :user="user" />
    <AdminImportsPage v-else-if="onImports" :user="user" />
    <FlagsPage v-else-if="flagScope" :user="user" :scope="flagScope" />
    <BookPage v-else-if="bookId" :id="bookId" :user="user" />
    <RecipeFormPage v-else-if="newRecipeFor" :book-id="newRecipeFor" />
    <BookEditPage v-else-if="editBookId" :id="editBookId" />
    <RecipeFormPage v-else-if="editRecipeId" :recipe-id="editRecipeId" />
    <RecipePage v-else-if="recipeId" :id="recipeId" :user="user" />
    <template v-else>
      <p v-if="signInFailed" class="sign-in-failed" role="alert">
        Sign-in didn't work. Please try again.
      </p>
      <HomePage />
    </template>
  </main>
  <footer class="site-footer">
    <div class="bar">
      <span
        >Catalog data under the
        <a href="https://opendatacommons.org/licenses/odbl/1-0/">ODbL</a></span
      >
      <a href="/api/docs">API</a>
      <a href="/privacy">Privacy</a>
      <a href="/terms">Terms</a>
      <span class="theme-choice">
        <label for="theme">Theme</label>
        <select id="theme" v-model="theme" @change="chooseTheme(theme)">
          <option value="system">Same as device</option>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </select>
      </span>
    </div>
  </footer>
</template>

<style>
/* The design's colours, once (Ray's wireframes, 2026-11-08): light as
   drawn, and dark when chosen in the footer or, by default, when the device
   is set to dark. data-theme on <html> is always "light" or "dark" (see
   index.html and theme.ts). --accent is the primary
   action (the blue Search button); --line is a divider, lighter than
   --border, which input edges use and which keeps 3:1 against --bg. */
:root {
  --bg: #ffffff;
  --surface: #f3f2ef;
  --fg: #1a1a19;
  --muted: #5f5e5a;
  --link: #1f5fbf;
  --accent: #1f5fbf;
  --accent-hover: #194f9f;
  --on-accent: #ffffff;
  --border: #8a877f;
  --line: #e3e2de;
  --chip: #e8eef7;
  --admin-bg: #fdf3d3;
  --admin-line: #ecd58a;
  --error: #b3261e;
  --page: 72rem;
  color-scheme: light;
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #161615;
  --surface: #22211f;
  --fg: #ecebe6;
  --muted: #a8a59c;
  --link: #8ab4f8;
  /* Light blue with dark text: white on it would be under 3:1. */
  --accent: #8ab4f8;
  --accent-hover: #a8c7fa;
  --on-accent: #0b1f3a;
  --border: #77746c;
  --line: #34332f;
  --chip: #1f2c40;
  --admin-bg: #3a3016;
  --admin-line: #5c4c1f;
  --error: #f2a8a2;
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  line-height: 1.5;
}
.site-header {
  border-bottom: 1px solid var(--line);
}
.site-header .bar,
.site-footer .bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem 1.75rem;
  max-width: var(--page);
  margin: 0 auto;
  padding: 0.75rem 1.5rem;
}
/* One logo per theme; the other is hidden. */
:root[data-theme="dark"] .brand .for-light,
:root:not([data-theme="dark"]) .brand .for-dark {
  display: none !important;
}
.theme-choice {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: auto;
}
.theme-choice select {
  font: inherit;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.brand img {
  display: block;
  height: 2.25rem;
  width: auto;
}
.primary-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1.25rem;
}
.primary-nav a {
  color: var(--fg);
  text-decoration: none;
  font-weight: 500;
}
.primary-nav a:hover {
  text-decoration: underline;
}
.primary-nav a[aria-current="page"] {
  font-weight: 700;
}
.account {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  margin-left: auto;
  font-size: 0.9375rem;
}
.account form {
  margin: 0;
}
.account a,
.account button {
  color: var(--fg);
  text-decoration: underline;
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  cursor: pointer;
}
.account a.button-outline,
a.button-outline {
  display: inline-block;
  padding: 0.375rem 0.875rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--fg);
  text-decoration: none;
  font-weight: 600;
}
/* On a phone the sections go on their own line, under the logo. */
@media (max-width: 40rem) {
  .site-header .bar {
    gap: 0.5rem 1rem;
    padding: 0.75rem 1rem;
  }
  .primary-nav {
    order: 3;
    width: 100%;
  }
  .brand img {
    height: 2rem;
  }
}
.site-footer {
  margin-top: 3rem;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 0.875rem;
}
.site-footer .bar {
  gap: 0.5rem 1.25rem;
  padding: 1.25rem 1.5rem 2rem;
}
.site-footer a {
  color: var(--link);
}
main > article,
main > section {
  max-width: 40rem;
  margin: 0 auto;
  padding: 2rem 1rem 0;
}
.sign-in-failed {
  max-width: var(--page);
  margin: 1rem auto 0;
  padding: 0 1.5rem;
  color: var(--error);
}

/* A page laid out to the full width, as the redesigned ones are. */
main > article.wide {
  max-width: var(--page);
  padding: 2rem 1.5rem 0;
  box-sizing: border-box;
}
button.secondary {
  font: inherit;
  padding: 0.5rem 1rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  cursor: pointer;
}
button.secondary:hover {
  background: var(--surface);
}
button.secondary[aria-current="page"] {
  border-color: var(--fg);
  font-weight: 700;
}
.chip-input {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  align-items: center;
  padding: 0.375rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  cursor: text;
}
.chip-input input {
  flex: 1 1 10rem;
  min-width: 0;
  border: none;
  padding: 0.25rem;
  font: inherit;
  background: transparent;
  color: var(--fg);
}
.chip-input input:focus {
  outline: none;
}
.chip-input:focus-within {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.25rem 0.125rem 0.5rem;
  border-radius: 6px;
  background: var(--chip);
  color: var(--fg);
  font-size: 0.9375rem;
}
.chip button {
  border: none;
  background: none;
  color: var(--fg);
  font: inherit;
  padding: 0 0.25rem;
  cursor: pointer;
}
.suggestions {
  list-style: none;
  margin: 0.25rem 0 0;
  padding: 0.25rem 0;
}
.suggestions li {
  margin: 0;
  padding: 0.125rem 0;
}

/* Search. */
.search-panel {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  padding: 1rem 1.25rem 1.25rem;
  border-radius: 8px;
  background: var(--surface);
}
.search-panel label,
.filters legend {
  font-weight: 600;
  font-size: 0.9375rem;
}
.search-panel .help {
  margin: 0;
  color: var(--muted);
  font-size: 0.875rem;
}
.search-panel .optional {
  font-weight: normal;
  color: var(--muted);
}
.panel-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 0.75rem 1rem;
  margin-top: 0.75rem;
}
.panel-row > div {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.panel-row > div > input {
  font: inherit;
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.search-body {
  display: grid;
  grid-template-columns: 12rem minmax(0, 1fr);
  gap: 2rem;
  margin-top: 1.5rem;
}
@media (max-width: 48rem) {
  .search-body {
    grid-template-columns: minmax(0, 1fr);
    gap: 1rem;
  }
}
.filters fieldset {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
  margin: 0;
  padding: 0;
  border: none;
}
.filters legend {
  margin-bottom: 0.375rem;
  padding: 0;
  color: var(--muted);
  font-size: 0.8125rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.filters .check {
  font-weight: normal;
}
.filters button.link,
.results a,
.search-page .suggestions button.link {
  color: var(--link);
}
.results-head {
  margin: 0 0 0.75rem;
  font-size: 1.125rem;
}
.muted {
  color: var(--muted);
  font-weight: normal;
}
.hits {
  list-style: none;
  margin: 0;
  padding: 0;
}
.hits .hit {
  display: flex;
  gap: 1rem;
  margin: 0 0 0.75rem;
  padding: 0.875rem 1rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.hit-cover {
  flex: none;
  width: 3rem;
  height: 4.5rem;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--surface);
  object-fit: cover;
}
.hit h3 {
  margin: 0 0 0.125rem;
  font-size: 1.0625rem;
}
.hit p {
  margin: 0.125rem 0 0;
  font-size: 0.9375rem;
}
.hit-where,
.hit-needs {
  color: var(--muted);
}
.hit-have {
  font-weight: 600;
}
.pager {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  align-items: center;
  justify-content: center;
  margin: 1.25rem 0 0;
}

/* The front page. */
.hero {
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}
.hero-inner {
  max-width: 44rem;
  margin: 0 auto;
  padding: 3.5rem 1.5rem 2.5rem;
}
.hero h1 {
  margin: 0 0 0.75rem;
  font-size: clamp(1.75rem, 5vw, 2.5rem);
  line-height: 1.15;
}
.lede {
  margin: 0 0 1.5rem;
  color: var(--muted);
  font-size: 1.0625rem;
}
.hero-search {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.25rem;
}
.hero-search input {
  flex: 1;
  min-width: 0;
  font: inherit;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.hero-search button.primary {
  align-self: stretch;
}
.hero-have .isbn-form {
  margin-bottom: 0.75rem;
}
.hero-have .chosen {
  margin-bottom: 0.75rem;
}
.hero-have .chosen li {
  background: var(--chip);
  border-color: transparent;
}
.hero-have .help {
  margin: 0.5rem 0 0;
  color: var(--muted);
  font-size: 0.875rem;
}
.home-section {
  max-width: var(--page);
  margin: 2.5rem auto 0;
  padding: 0 1.5rem;
  box-sizing: border-box;
}
.section-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem 1rem;
}
.section-head h2 {
  margin: 0 0 1rem;
  font-size: 1.25rem;
}
.section-head a,
.value-cards a {
  color: var(--link);
}
.cover-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
  gap: 1.5rem 1.25rem;
  list-style: none;
  padding: 0;
  margin: 0;
}
.cover-grid li {
  margin: 0;
}
.cover-card {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  color: var(--fg);
  text-decoration: none;
}
.cover-card img,
.cover-card .cover-blank {
  width: 100%;
  aspect-ratio: 2 / 3;
  object-fit: cover;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--surface);
  box-sizing: border-box;
  margin-bottom: 0.5rem;
}
.cover-card .cover-blank {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  font-size: 0.8125rem;
}
.cover-card:hover strong {
  text-decoration: underline;
}
.cover-card .kind {
  color: var(--muted);
  font-size: 0.75rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.cover-card .byline {
  color: var(--muted);
  font-size: 0.8125rem;
}
.value-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 1rem;
}
.value-cards > div {
  padding: 1rem 1.25rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.value-cards h3 {
  margin: 0 0 0.375rem;
  font-size: 1rem;
}
.value-cards p {
  margin: 0;
  color: var(--muted);
  font-size: 0.9375rem;
}
.status,
.updated {
  color: var(--muted);
  font-size: 0.875rem;
}
main a {
  color: var(--fg);
}
main li {
  margin-bottom: 0.5rem;
}
main h2 {
  margin-top: 2rem;
  font-size: 1.125rem;
}
.name-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 24rem;
}
.name-form label {
  font-weight: 600;
}
.name-form input {
  font: inherit;
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.name-form .help {
  margin: 0;
  color: var(--muted);
  font-size: 0.875rem;
}
.name-form .error {
  margin: 0;
  color: var(--error);
}
button.primary {
  align-self: flex-start;
  font: inherit;
  font-weight: 600;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 8px;
  background: var(--accent);
  color: var(--on-accent);
  cursor: pointer;
}
button.primary:hover {
  background: var(--accent-hover);
}
button.primary:disabled {
  opacity: 0.6;
  cursor: default;
}
.isbn-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 2rem;
}
.isbn-form label {
  font-weight: 600;
}
.isbn-form .row {
  display: flex;
  gap: 0.5rem;
}
.isbn-form input {
  flex: 1;
  min-width: 0;
  font: inherit;
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.isbn-form .error {
  margin: 0;
  color: var(--error);
}
.book-list {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 0.75rem;
}
.book-card {
  display: flex;
  gap: 0.875rem;
  align-items: center;
  color: var(--fg);
  text-decoration: none;
}
.book-card:hover strong {
  text-decoration: underline;
}
.book-card img,
.book-card .no-cover {
  width: 48px;
  height: 72px;
  object-fit: cover;
  border-radius: 4px;
  flex: none;
  background: var(--border);
}
.byline,
.subtitle {
  display: block;
  color: var(--muted);
}
.book-head {
  display: flex;
  gap: 1.25rem;
  align-items: flex-start;
}
.book-head img {
  width: 120px;
  border-radius: 4px;
  flex: none;
}
.book-head h1 {
  margin-top: 0;
}
@media (max-width: 480px) {
  .book-head {
    flex-direction: column;
  }
}
.editions li,
.recipe-list li {
  margin-bottom: 0.5rem;
}
.recipe-list a {
  color: var(--fg);
}
.page-ref {
  margin-left: 0.5rem;
  color: var(--muted);
  font-size: 0.875rem;
}
.ol-link {
  margin-top: 2rem;
}
.ol-link .isbn-form {
  margin-bottom: 1rem;
}
.ol-preview ul {
  padding-left: 1.25rem;
}
.ol-preview li {
  margin-bottom: 0.25rem;
}
.ol-differences {
  list-style: none;
  padding: 0;
}
.ol-differences li {
  margin-bottom: 0.75rem;
}
.ol-values,
.ol-covers {
  display: block;
  margin-left: 1.75rem;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.ol-values .theirs {
  color: var(--fg);
}
.ol-covers img {
  width: 48px;
  vertical-align: middle;
  border-radius: 4px;
}
.ol-link .error {
  color: var(--error);
}
.recipe-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 32rem;
}
.recipe-form > label,
.recipe-form > .form-heading {
  font-weight: 600;
  margin: 0.75rem 0 0;
}
.recipe-form input:not([type="checkbox"]),
.recipe-form textarea {
  font: inherit;
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.recipe-form fieldset {
  border: none;
  padding: 0;
  margin: 0.75rem 0 0;
}
.recipe-form legend {
  font-weight: 600;
  padding: 0;
}
.recipe-form .help {
  margin: 0;
  color: var(--muted);
  font-size: 0.875rem;
}
.recipe-form > label.check {
  font-weight: normal;
}
.family-add {
  margin: 1rem 0 1.5rem;
}
.family-add summary {
  cursor: pointer;
  font-weight: 600;
}
.family-add .recipe-form {
  margin-top: 0.75rem;
}
/* What a family collection keeps and who sees it, before the tick box. */
.notice {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.25rem 0.875rem;
  font-size: 0.9375rem;
}
.notice p {
  margin: 0.5rem 0;
}
.inline-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin: 0.5rem 0;
}
.inline-form input {
  font: inherit;
  padding: 0.375rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  min-width: 0;
  flex: 1 1 12rem;
}
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
.recipe-form .error {
  color: var(--error);
}
.line-hints {
  margin: 0;
  padding-left: 1.25rem;
  font-size: 0.875rem;
}
.line-hints li {
  margin-bottom: 0.375rem;
}
.line-hints button {
  margin-left: 0.375rem;
}
.credit-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin-top: 0.5rem;
}
.credit-row input {
  flex: 1 1 12rem;
  min-width: 0;
}
.credit-row select,
.recipe-form select {
  font: inherit;
  padding: 0.375rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.recipe-form fieldset > button.link {
  margin-top: 0.5rem;
}
.edition-edit {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.edition-row {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
  margin-top: 0.5rem;
}
.edition-row .check,
.edition-row .only-edition {
  flex: 1;
  min-width: 0;
}
.recipe-list li > button.link {
  margin-left: 0.75rem;
}
.member-list {
  list-style: none;
  padding: 0;
}
.member-list li {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
  align-items: center;
  margin-bottom: 0.5rem;
}
.member-list li > span:first-child {
  flex: 1 1 10rem;
}
.member-list select {
  font: inherit;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.episode-numbers {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
  align-items: center;
  margin-top: 0.75rem;
}
.episode-numbers > span {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.episode-numbers label {
  font-weight: 600;
}
.recipe-form .page-input {
  width: 6rem;
  flex: none;
}
.recipe-form .page-input:disabled {
  opacity: 0.5;
}
progress {
  width: 100%;
  accent-color: var(--accent);
}
.flag-list {
  list-style: none;
  padding: 0;
}
.flag {
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--border);
}
.flag p {
  margin: 0.25rem 0;
}
.flag-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  margin: 1rem 0;
}
.flag-filters select,
.dismiss input {
  font: inherit;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.dismiss {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  max-width: 24rem;
}
.recipe-flags .admin-actions,
.flag .admin-actions {
  margin-top: 0.25rem;
}
.run-list > li {
  margin-bottom: 1.5rem;
}
.admin-actions {
  display: flex;
  gap: 1rem;
  margin-top: 2rem;
}
.admin-actions a,
button.link {
  color: var(--fg);
  text-decoration: underline;
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  cursor: pointer;
}
.aliases {
  color: var(--muted);
}
.remove-alias {
  margin-left: 0.125rem;
  padding: 0 0.25rem;
  color: var(--muted);
}
.fix-ingredient {
  margin-top: 2.5rem;
  border-top: 1px solid var(--border);
}
.fix-ingredient .error {
  color: var(--error);
}
.recipe-list .match {
  display: block;
  color: var(--muted);
  font-size: 0.875rem;
}
.author-links {
  list-style: none;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
}
.merge-here {
  margin-left: 0.5rem;
}
.author-merge {
  margin-top: 1.5rem;
}
.author-link-form {
  margin-top: 1.5rem;
}
.web-address {
  overflow-wrap: anywhere;
}
.byline a {
  color: inherit;
}
.swap-list {
  padding-left: 1.25rem;
}
.swap-list li {
  margin-bottom: 0.5rem;
}
.swap-note {
  display: block;
  color: var(--muted);
  font-size: 0.875rem;
}
.swap-form {
  margin-top: 1rem;
}
.swap-form fieldset {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
}
.swap-form fieldset > label:not(.check) {
  font-weight: 600;
  margin-top: 0.5rem;
}
.swap-form fieldset > .isbn-form {
  align-self: stretch;
  margin-bottom: 0;
}
.swap-form .check {
  font-weight: normal;
}
.swap-form select {
  max-width: 100%;
}
.chosen {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  list-style: none;
  padding: 0;
  margin: 0 0 1.5rem;
}
.chosen li {
  margin: 0;
  padding: 0.25rem 0.375rem 0.25rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 999px;
}
.chosen button {
  margin-left: 0.25rem;
  padding: 0 0.25rem;
}
.merge-candidates {
  list-style: none;
  padding: 0;
  margin: 0;
}
</style>
