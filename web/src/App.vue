<script setup lang="ts">
import { adoptAccount } from "./shops";
import { computed, onMounted, ref } from "vue";
import NameForm from "./components/NameForm.vue";
import { takeRememberedInvite } from "./groups";
import { chooseTheme, savedTheme, type ThemeChoice } from "./theme";
import type { Me } from "./me";
import AccountPage from "./pages/AccountPage.vue";
import AdminApiUsagePage from "./pages/AdminApiUsagePage.vue";
import AdminChangesPage from "./pages/AdminChangesPage.vue";
import AdminClicksPage from "./pages/AdminClicksPage.vue";
import AdminPeoplePage from "./pages/AdminPeoplePage.vue";
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
import BulkEntryPage from "./pages/BulkEntryPage.vue";
import BooksPage from "./pages/BooksPage.vue";
import RecipeFormPage from "./pages/RecipeFormPage.vue";
import RecipePage from "./pages/RecipePage.vue";
import RequestsPage from "./pages/RequestsPage.vue";
import SearchPage from "./pages/SearchPage.vue";
import SuggestionsPage from "./pages/SuggestionsPage.vue";
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
const onSuggestions = path === "/admin/suggestions";
const onApiUsage = path === "/admin/api";
const onClicks = path === "/admin/clicks";
const onPeople = path === "/admin/people";
const onChanges = path === "/admin/changes";
const onRequests = path === "/requests";
const flagScope = ({ "/admin/flags": "all", "/account/flags": "mine" } as const)[path];
const UUID = "([0-9a-f-]{36})";
const match = (pattern: string) => path.match(new RegExp(`^${pattern}$`, "i"))?.[1] ?? null;
const bookId = match(`/sources/${UUID}`);
const newRecipeFor = match(`/sources/${UUID}/recipes/new`);
const editBookId = match(`/sources/${UUID}/edit`);
const bulkFor = match(`/sources/${UUID}/bulk`);
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
  { href: "/requests", label: "Requests" },
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
    adoptAccount(user.value);
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
        <img class="for-light" src="/logo-light.svg" alt="OpenLarder" width="150" height="44" />
        <img class="for-dark" src="/logo-dark.svg" alt="OpenLarder" width="150" height="44" />
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
          <a v-if="user.may_edit" href="/admin">Admin</a>
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
  <!-- A page's admin tools go here, under the header (BookPage's Teleport). -->
  <div id="admin-bar"></div>
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
    <SuggestionsPage v-else-if="onSuggestions" :user="user" />
    <AdminApiUsagePage v-else-if="onApiUsage" :user="user" />
    <AdminClicksPage v-else-if="onClicks" :user="user" />
    <AdminPeoplePage v-else-if="onPeople" :user="user" />
    <AdminChangesPage v-else-if="onChanges" :user="user" />
    <RequestsPage v-else-if="onRequests" :user="user" />
    <FlagsPage v-else-if="flagScope" :user="user" :scope="flagScope" />
    <BookPage v-else-if="bookId" :id="bookId" :user="user" />
    <RecipeFormPage v-else-if="newRecipeFor" :book-id="newRecipeFor" :user="user" />
    <BookEditPage v-else-if="editBookId" :id="editBookId" />
    <BulkEntryPage v-else-if="bulkFor" :id="bulkFor" />
    <RecipeFormPage v-else-if="editRecipeId" :recipe-id="editRecipeId" :user="user" />
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
/* The brand's type (the brand kit, made with Claude for Ray, 2026-11-09): Outfit, served from here
   rather than a font service, so no one else hears of a visit. */
@font-face {
  font-family: "Outfit";
  font-weight: 300;
  font-style: normal;
  font-display: swap;
  src: url("/fonts/outfit-300.woff2") format("woff2");
}
@font-face {
  font-family: "Outfit";
  font-weight: 400;
  font-style: normal;
  font-display: swap;
  src: url("/fonts/outfit-400.woff2") format("woff2");
}
@font-face {
  font-family: "Outfit";
  font-weight: 700;
  font-style: normal;
  font-display: swap;
  src: url("/fonts/outfit-700.woff2") format("woff2");
}

/* The brand's colours, once: the kit's THEMES.md (2026-11-09), light and dark.
   data-theme on <html> is always "light" or "dark" (see index.html and
   theme.ts). The kit's tokens map onto these: --bg, --surface (cards,
   panels, bands), --fg, --muted, --accent (its primary: buttons), --link,
   --line (its border: hairlines) and --focus. Two the kit leaves to the
   site: --border, input and button edges, which must keep 3:1 against
   --bg and so is darker than the kit's hairline; and the tints for chips,
   admin bands, "fine" tags and errors, drawn from its colours. Light links
   are only just 4.5:1 on ivory, so they're never set on a band darker than
   it. test_colour_tokens.py checks every pair a page puts together. */
:root {
  --bg: #faf6ec;
  --surface: #ffffff;
  --fg: #2e4a3b;
  --muted: #56665c;
  --link: #b5532c;
  --accent: #2e4a3b;
  --accent-hover: #1f3329;
  --on-accent: #faf6ec;
  --focus: #b5532c;
  --border: #8a8775;
  --line: #e4ddcb;
  --chip: #f3e4c2;
  --ok-bg: #e1ebdf;
  --admin-bg: #f6e3b8;
  --admin-line: #e8b866;
  --error: #a8321e;
  --page: 72rem;
  color-scheme: light;
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #14201a;
  --surface: #1c2b23;
  --fg: #f2ede0;
  --muted: #a9b5ac;
  --link: #e58b63;
  --accent: #e8b866;
  --accent-hover: #f0c987;
  --on-accent: #14201a;
  --focus: #e8b866;
  --border: #6f8577;
  --line: #34493d;
  --chip: #24372d;
  --ok-bg: #22402e;
  --admin-bg: #3a3218;
  --admin-line: #6b5520;
  --error: #f2a8a2;
}
:focus-visible {
  outline: 2px solid var(--focus);
  outline-offset: 2px;
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: "Outfit", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  line-height: 1.55;
}
h1,
h2,
h3 {
  letter-spacing: -0.02em;
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
  height: 2.75rem;
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
    height: 2.25rem;
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
button.secondary:disabled {
  opacity: 0.45;
  cursor: default;
}
button.secondary:disabled:hover {
  background: var(--bg);
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
.search-panel .panel-gap {
  margin-top: 0.75rem;
}
/* What you're leaving out: struck through, so it reads as "not this". */
.chip-unwanted {
  text-decoration: line-through;
  text-decoration-thickness: 1px;
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
/* The tag filters, after the source kinds. */
.filters fieldset + fieldset {
  margin-top: 1.25rem;
}
.filters > button.link {
  margin-top: 0.75rem;
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

/* The yellow band of admin tools under the header, from the wireframes. */
.admin-bar {
  background: var(--admin-bg);
  border-bottom: 1px solid var(--admin-line);
  font-size: 0.9375rem;
}
.admin-bar .bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.375rem 1.25rem;
  max-width: var(--page);
  margin: 0 auto;
  padding: 0.5rem 1.5rem;
}
.admin-bar a {
  color: var(--fg);
}
.admin-bar a[aria-current="page"] {
  font-weight: 700;
  text-decoration: none;
}
.crumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-bottom: 1.5rem;
  color: var(--muted);
  font-size: 0.875rem;
}
.crumbs a {
  color: var(--link);
}

/* A source's page. */
.source-head {
  display: grid;
  grid-template-columns: 9rem minmax(0, 1fr) 16rem;
  gap: 1.5rem;
  align-items: start;
}
@media (max-width: 56rem) {
  .source-head {
    grid-template-columns: 6rem minmax(0, 1fr);
  }
  .source-side {
    grid-column: 1 / -1;
  }
}
/* Beside the cover: where to buy the selected edition, then elsewhere. */
.source-side {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.source-buy {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem 1rem 1rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.source-buy h2 {
  margin: 0;
  font-size: 1rem;
}
.source-buy .buy-edition {
  margin: -0.25rem 0 0.25rem;
  color: var(--muted);
  font-size: 0.8125rem;
}
.source-buy .button-outline {
  display: block;
  text-align: center;
}
.source-buy .buy-note {
  margin: 0.125rem 0 0;
}
/* Choosing the shops, under the buttons. */
.shop-chooser {
  margin-top: 0.5rem;
  font-size: 0.875rem;
}
.shop-chooser summary {
  color: var(--link);
  cursor: pointer;
  text-decoration: underline;
}
.shop-chooser .help {
  margin: 0.5rem 0;
  color: var(--muted);
}
.shop-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.shop-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding: 0.25rem 0;
  border-top: 1px solid var(--line);
}
.shop-list label {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}
.shop-moves {
  display: flex;
  gap: 0.25rem;
}
.source-cover {
  width: 100%;
  aspect-ratio: 2 / 3;
  object-fit: cover;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--surface);
  box-sizing: border-box;
}
.source-about h1 {
  margin: 0.125rem 0 0.25rem;
  font-size: clamp(1.5rem, 4vw, 2rem);
  line-height: 1.2;
}
.source-about p {
  margin: 0.25rem 0;
}
.source-about .kind {
  color: var(--muted);
  font-size: 0.75rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.source-about .credits a,
.source-elsewhere a,
.source-section a,
.credit-line a {
  color: var(--link);
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  list-style: none;
  margin: 0.5rem 0;
  padding: 0;
}
.tags li {
  margin: 0;
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  background: var(--surface);
  font-size: 0.8125rem;
}
.source-about .actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.source-elsewhere {
  padding: 0.75rem 1rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.source-elsewhere h2 {
  margin: 0 0 0.375rem;
  font-size: 1rem;
}
.source-elsewhere p {
  margin: 0.25rem 0;
}
.source-section {
  margin-top: 2rem;
}
.source-section h2 {
  margin: 0 0 0.5rem;
  font-size: 1.125rem;
}
.edition-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0 0.25rem;
  border-bottom: 1px solid var(--line);
}
.edition-tabs button {
  font: inherit;
  font-size: 0.9375rem;
  padding: 0.5rem 0.75rem;
  border: none;
  border-bottom: 3px solid transparent;
  background: none;
  color: var(--muted);
  cursor: pointer;
}
.edition-tabs button[aria-pressed="true"] {
  border-bottom-color: var(--accent);
  color: var(--fg);
  font-weight: 700;
}
.edition-facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 0.75rem 1.5rem;
  margin: 0.75rem 0 0;
}
.edition-facts dt {
  color: var(--muted);
  font-size: 0.8125rem;
}
.edition-facts dd {
  margin: 0;
}
.ingredient-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  list-style: none;
  padding: 0;
  margin: 0;
}
.ingredient-chips li {
  margin: 0;
  padding: 0.25rem 0.75rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  font-size: 0.9375rem;
}
.ingredient-chips .count {
  margin-left: 0.375rem;
  color: var(--muted);
}
.chip-toggle {
  font: inherit;
  border: none;
  background: none;
  color: var(--fg);
  padding: 0;
  cursor: pointer;
}
.table-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem 1rem;
  margin-bottom: 0.5rem;
}
.table-head h2 {
  margin: 0;
}
.table-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.table-controls input,
.table-controls select {
  font: inherit;
  padding: 0.375rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  min-width: 0;
}
.recipe-table {
  width: 100%;
  border-collapse: collapse;
  border: 1px solid var(--line);
  font-size: 0.9375rem;
}
.recipe-table th {
  background: var(--surface);
  text-align: left;
  font-weight: 600;
}
.recipe-table th,
.recipe-table td {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
.recipe-table td:first-child {
  white-space: nowrap;
}
.recipe-table .lines {
  color: var(--muted);
}
.recipe-table .chapter-note {
  font-size: 0.8125rem;
}
.buy-links {
  margin-top: 0.75rem;
}
.buy-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.375rem 0.75rem;
  margin: 0;
}
.buy-row a {
  color: var(--link);
}
.buy-note {
  margin: 0.375rem 0 0;
  color: var(--muted);
  font-size: 0.8125rem;
}
.find-chapter {
  margin: 0.5rem 0 0;
  color: var(--muted);
  font-size: 0.875rem;
}
/* On a phone each row becomes a small card. */
@media (max-width: 40rem) {
  .recipe-table thead {
    display: none;
  }
  .recipe-table tr {
    display: block;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--line);
  }
  .recipe-table,
  .recipe-table tbody {
    display: block;
  }
  .recipe-table td,
  .recipe-table td:first-child {
    display: block;
    padding: 0.125rem 0;
    border: none;
    white-space: normal;
  }
}
.badge {
  display: inline-block;
  margin-left: 0.5rem;
  padding: 0 0.375rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--muted);
  font-size: 0.75rem;
}
.table-foot {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.25rem 1rem;
  margin-top: 0.5rem;
}
.table-foot .status {
  margin: 0;
}
.table-foot button.link {
  color: var(--link);
}
.credit-line {
  margin-top: 2rem;
}

/* A recipe's page. */
.recipe-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
}
.recipe-title h1 {
  margin: 0;
  font-size: clamp(1.5rem, 4vw, 2rem);
  line-height: 1.2;
}
.recipe-title .badge {
  margin: 0;
}
.recipe-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 16rem;
  gap: 2rem;
  margin-top: 1.25rem;
}
@media (max-width: 56rem) {
  .recipe-layout {
    grid-template-columns: minmax(0, 1fr);
    gap: 1rem;
  }
}
.find-it {
  display: flex;
  gap: 1rem;
  padding: 1rem 1.25rem;
  border-radius: 8px;
  background: var(--surface);
}
.find-cover {
  flex: none;
  width: 4rem;
  height: 6rem;
  object-fit: cover;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--bg);
}
.find-about {
  min-width: 0;
}
.find-about p {
  margin: 0.125rem 0;
}
.find-label {
  color: var(--muted);
  font-size: 0.8125rem;
}
.find-source {
  font-size: 1.125rem;
  font-weight: 700;
}
.find-about a {
  color: var(--link);
}
.find-place {
  margin-top: 0.375rem !important;
  font-size: 1.375rem;
  font-weight: 700;
}
.find-place .web-address {
  font-size: 1rem;
  font-weight: normal;
  overflow-wrap: anywhere;
}
.find-edition {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.25rem 0.75rem;
}
.find-edition label,
.find-edition-only {
  color: var(--muted);
  font-size: 0.875rem;
}
.find-edition select {
  font: inherit;
  font-size: 0.9375rem;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  max-width: 100%;
}
.reference-note {
  color: var(--muted);
  font-size: 0.9375rem;
}
.recipe-section {
  margin-top: 1.75rem;
}
.recipe-section h2 {
  margin: 0;
  font-size: 1.125rem;
}
.recipe-section .table-head {
  margin-bottom: 0.625rem;
}
.copy-list {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
}
.ingredient-lines {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.ingredient-lines li {
  margin: 0;
  padding: 0.625rem 0.875rem;
  border-bottom: 1px solid var(--line);
}
.ingredient-lines li:last-child {
  border-bottom: none;
}
.ingredient-lines a,
.recipe-section button.link {
  color: var(--link);
}
.used-in {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}
.used-in .page-ref {
  white-space: nowrap;
}
.recipe-aside {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.flag-box {
  padding: 0.75rem 1rem;
  border: 1px solid var(--admin-line);
  border-radius: 8px;
  background: var(--admin-bg);
}
.flag-box h2 {
  margin: 0 0 0.375rem;
  font-size: 1rem;
}
.recipe-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}
.recipe-actions button.link {
  color: var(--link);
}
.added-by {
  margin: 0;
  padding-top: 0.75rem;
  border-top: 1px solid var(--line);
}

/* An ingredient's page and an author's. */
.ingredient-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem 1.5rem;
}
.ingredient-head h1,
.author-head h1 {
  margin: 0 0 0.25rem;
  font-size: clamp(1.5rem, 4vw, 2rem);
  line-height: 1.2;
}
.ingredient-head .status {
  margin: 0;
}
a.button-primary {
  display: inline-block;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  background: var(--accent);
  color: var(--on-accent);
  font-weight: 600;
  text-decoration: none;
}
a.button-primary:hover {
  background: var(--accent-hover);
}
.ingredient-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
  gap: 1rem;
  margin-top: 1.25rem;
}
.ingredient-cards > div {
  padding: 0.75rem 1rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.ingredient-cards h2 {
  margin: 0 0 0.25rem;
  color: var(--muted);
  font-size: 0.875rem;
  font-weight: 600;
}
.ingredient-cards p {
  margin: 0;
}
.ingredient-cards a,
.author-head a,
.cover-card + .byline a {
  color: var(--link);
}
.recipe-table a.strong {
  font-weight: 600;
}
.show-more {
  margin-top: 0.75rem;
}
.author-facts {
  margin: 0 0 0.5rem;
  color: var(--muted);
}
.author-wikidata .help {
  margin: 0;
  color: var(--muted);
  font-size: 0.875rem;
}
.clash-list {
  margin: 0;
  padding-left: 1.25rem;
  font-size: 0.9375rem;
}
.clash-list a {
  color: var(--link);
}
.author-head .kind {
  margin: 0;
  color: var(--muted);
  font-size: 0.75rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.author-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1.25rem;
  list-style: none;
  margin: 0.5rem 0 0;
  padding: 0;
}
.author-links li {
  margin: 0;
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
/* The list pages: Sources, Ingredients, Authors. */
.list-head h1 {
  margin: 0 0 0.25rem;
}
.list-head .muted a {
  color: var(--link);
}
.add-panels {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: flex-start;
  margin: 1.25rem 0 0;
}
.add-panel {
  flex: 0 1 auto;
}
.add-panel[open] {
  flex: 1 1 100%;
  padding: 0 1rem 1rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.add-panel > summary {
  display: inline-block;
  padding: 0.375rem 0.875rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9375rem;
  list-style: none;
}
.add-panel > summary::-webkit-details-marker {
  display: none;
}
.add-panel > summary::before {
  content: "+ ";
}
.add-panel[open] > summary {
  margin: 0.75rem 0;
  padding: 0;
  border: none;
  font-weight: 600;
}
.add-panel[open] > summary::before {
  content: "− ";
}
.add-panel .isbn-form {
  max-width: 32rem;
  margin-bottom: 0;
}
.list-tools {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-end;
  gap: 0.75rem 1.5rem;
  margin: 1.5rem 0 0.75rem;
}
.list-find {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  flex: 1 1 18rem;
  max-width: 32rem;
}
.list-find label {
  font-weight: 600;
}
.list-find input {
  font: inherit;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.kind-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.kind-filter .count {
  margin-left: 0.25rem;
  color: var(--muted);
}
button.secondary[aria-pressed="true"] {
  border-color: var(--fg);
  background: var(--fg);
  color: var(--bg);
}
button.secondary[aria-pressed="true"] .count {
  color: inherit;
}
.ingredient-list .numeric,
.author-list .numeric {
  text-align: right;
}
.cell-label {
  display: none;
}
@media (max-width: 40rem) {
  .cell-label {
    display: inline;
    color: var(--muted);
  }
  .ingredient-list td.empty,
  .author-list td.empty {
    display: none;
  }
  .ingredient-list .numeric,
  .author-list .numeric {
    text-align: left;
  }
  .author-list td.numeric {
    display: inline-block;
    margin-right: 1rem;
  }
}
.results-count {
  margin: 0 0 1rem;
}.cover-grid {
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
/* Adding a recipe: four steps, then a box per ingredient line with its
   check beside it (Ray's wireframe). */
.steps {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  list-style: none;
  padding: 0;
  margin: 0 0 1.5rem;
}
.steps li {
  margin: 0;
}
.step {
  font: inherit;
  font-size: 0.875rem;
  padding: 0.375rem 0.875rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg);
  color: var(--fg);
  cursor: pointer;
}
.step[aria-current="step"] {
  border-color: var(--fg);
  background: var(--fg);
  color: var(--bg);
  font-weight: 600;
}
.step:disabled {
  border-color: var(--line);
  color: var(--muted);
  cursor: default;
}
.add-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 17rem;
  gap: 2rem;
  align-items: start;
}
.add-layout.solo {
  grid-template-columns: minmax(0, 48rem);
}
@media (max-width: 52rem) {
  .add-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
.add-recipe h2 {
  margin: 0 0 0.5rem;
  font-size: 1.125rem;
}
.add-recipe h2:focus {
  outline: none;
}
.add-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.5rem 1.25rem;
  align-items: start;
  margin: 0 0 1.5rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.add-summary dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem 1.25rem;
  margin: 0;
}
.add-summary dt {
  color: var(--muted);
  font-size: 0.8125rem;
}
.add-summary dd {
  margin: 0;
  overflow-wrap: anywhere;
}
@media (max-width: 40rem) {
  .add-summary,
  .add-summary dl {
    grid-template-columns: minmax(0, 1fr);
  }
  .add-summary button {
    justify-self: start;
  }
}
.add-recipe .help {
  color: var(--muted);
  font-size: 0.875rem;
}
.line-rows {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  list-style: none;
  padding: 0;
  margin: 1rem 0;
}
.line-row {
  margin: 0;
  padding: 0.75rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.line-main {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 0.5rem 0.75rem;
  align-items: start;
}
@media (max-width: 40rem) {
  .line-main {
    grid-template-columns: minmax(0, 1fr);
  }
}
.line-input {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.line-input input {
  flex: 1;
  min-width: 0;
  font: inherit;
  padding: 0.5rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.remove-line {
  padding: 0 0.375rem;
  font-size: 1.375rem;
  line-height: 1;
  text-decoration: none;
}
.line-tag {
  margin: 0;
  padding: 0.5rem 0.625rem;
  border-radius: 6px;
  color: var(--fg);
  font-size: 0.875rem;
}
.tone-ok {
  background: var(--ok-bg);
}
.tone-info {
  background: var(--chip);
}
.tone-warn {
  background: var(--admin-bg);
}
.line-options {
  margin: 0.5rem 0 0;
  padding-left: 1.25rem;
  font-size: 0.875rem;
}
.line-options li {
  margin-bottom: 0.125rem;
}
.line-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin-top: 0.5rem;
  font-size: 0.875rem;
}
button.secondary.small,
button.primary.small {
  padding: 0.25rem 0.625rem;
  font-size: 0.875rem;
}

/* The admin pages: cards to each, filters, tables and panels. */
.list-filters {
  margin: 1.25rem 0 0.25rem;
}
.list-filters .kind-filter {
  margin-bottom: 0.75rem;
}
.link-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
  gap: 1rem;
  margin: 1.5rem 0 0;
  padding: 0;
  list-style: none;
}
.link-cards li {
  margin: 0;
}
.link-cards a {
  display: block;
  height: 100%;
  padding: 1rem 1.25rem;
  border: 1px solid var(--line);
  border-radius: 8px;
  box-sizing: border-box;
  color: var(--fg);
  text-decoration: none;
}
.link-cards a:hover {
  border-color: var(--border);
  background: var(--surface);
}
.link-cards h2 {
  margin: 0 0 0.25rem;
  color: var(--link);
  font-size: 1.0625rem;
  text-decoration: underline;
}
.link-cards p {
  margin: 0;
  color: var(--muted);
  font-size: 0.9375rem;
}
.link-cards .count {
  margin-bottom: 0.375rem;
  color: var(--fg);
  font-weight: 600;
}
.section-title {
  margin: 2.5rem 0 1rem;
  font-size: 1.25rem;
}
.tool-panels {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(20rem, 1fr));
  gap: 1rem;
}
.tool-panel {
  padding: 1rem 1.25rem 1.25rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.tool-panel h2,
.tool-panel h3 {
  margin: 0 0 0.375rem;
  font-size: 1rem;
}
.account-panels {
  margin-top: 2rem;
}
/* Requests for books: the ask form, then the list with votes on the left. */
.request-ask {
  margin-bottom: 1.5rem;
}
.request-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  align-items: flex-start;
  justify-content: space-between;
}
.request-sort {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.request-sort select {
  font: inherit;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.request-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.request-list > li {
  display: grid;
  grid-template-columns: 3.5rem minmax(0, 1fr) auto;
  gap: 0.75rem 1rem;
  align-items: start;
  padding: 1rem 0;
  border-top: 1px solid var(--line);
}
.request-votes {
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 0.8125rem;
  color: var(--muted);
}
.request-votes strong {
  font-size: 1.375rem;
  color: var(--fg);
}
.request-title {
  font-size: 1.125rem;
  margin: 0;
}
.request-body p {
  margin: 0.25rem 0 0;
}
.request-note {
  font-style: italic;
}
.request-state {
  font-size: 0.875rem;
}
.request-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: flex-end;
}
@media (max-width: 40rem) {
  .request-list > li {
    grid-template-columns: 3rem minmax(0, 1fr);
  }
  .request-actions {
    grid-column: 2;
    justify-content: flex-start;
  }
}
.people-table select {
  font: inherit;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
/* Edit history: on each record's page, folded away, and Recent changes. */
.history-panel {
  margin-top: 2rem;
  border-top: 1px solid var(--line);
  padding-top: 1rem;
}
.history-panel summary {
  cursor: pointer;
  font-weight: 600;
}
.change-list {
  list-style: none;
  padding: 0;
  margin: 0.75rem 0 0;
}
.change-list > li {
  padding: 0.75rem 0;
  border-bottom: 1px solid var(--line);
}
.change-head {
  margin: 0 0 0.25rem;
}
.change-entries,
.change-fields {
  margin: 0;
  padding-left: 1.25rem;
  font-size: 0.9375rem;
  overflow-wrap: anywhere;
}
.change-fields {
  color: var(--muted);
}
.change-action {
  font-weight: 600;
}
.change-action.removed {
  color: var(--error);
}
/* Admin monitoring: API usage and buy-link clicks. */
.usage-table .numeric,
.people-table .numeric,
.clicks-panels .numeric {
  text-align: right;
}
.usage-table td.warn {
  color: var(--error);
  font-weight: 700;
}
.clicks-panels {
  margin-top: 1rem;
}
.clicks-panels .tool-panel h2 {
  margin-bottom: 0.75rem;
}
.day-bars {
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 0.875rem;
}
.day-bars li {
  display: grid;
  grid-template-columns: 4.5rem minmax(0, 1fr) 3rem;
  align-items: center;
  gap: 0.5rem;
  padding: 0.125rem 0;
}
.day-bar {
  height: 0.75rem;
  min-width: 2px;
  border-radius: 3px;
  background: var(--accent);
}
.day-count {
  text-align: right;
}
@media (max-width: 40rem) {
  .usage-table .numeric,
  .people-table .numeric,
  .clicks-panels .numeric {
    text-align: left;
  }
}
.api-keys {
  margin-top: 1rem;
}
.api-keys .muted a {
  color: var(--link);
}
.key-list {
  margin: 0 0 1rem;
  padding: 0;
  list-style: none;
}
.key-list li {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem 1rem;
  padding: 0.5rem 0;
  border-top: 1px solid var(--line);
}
.key-list .muted {
  font-size: 0.875rem;
}
.key-form input {
  font: inherit;
  flex: 1 1 14rem;
  padding: 0.375rem 0.625rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
/* Tags: chips under a title, each a search; and choosing them. */
.tag-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin: 0.5rem 0;
  padding: 0;
  list-style: none;
}
.tag-chips li {
  margin: 0;
}
.tag-chips a {
  display: inline-block;
  padding: 0.125rem 0.625rem;
  border-radius: 999px;
  background: var(--chip);
  color: var(--fg);
  font-size: 0.875rem;
  text-decoration: none;
}
.tag-chips a:hover {
  text-decoration: underline;
}
.tag-chip {
  display: inline-block;
  padding: 0.125rem 0.625rem;
  border-radius: 999px;
  background: var(--chip);
  color: var(--fg);
  font-size: 0.875rem;
}
.tag-editor {
  margin: 0.25rem 0 0.75rem;
}
.tag-editor[open] {
  max-width: 48rem;
}
.tag-kind {
  margin: 0 0 0.75rem;
  padding: 0;
  border: 0;
}
.tag-kind legend {
  margin-bottom: 0.375rem;
  font-weight: 600;
}
.tag-kind .kind-filter {
  margin: 0;
}
.tag-editor .help {
  color: var(--muted);
  font-size: 0.875rem;
}
.tag-new {
  margin-top: 1rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--line);
}
.tag-new label {
  font-weight: 600;
}
.tag-new select,
.tag-new input {
  font: inherit;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
/* Groups: the list, a group's page and an invite. */
.group-form {
  max-width: 32rem;
}
.group-table .numeric {
  text-align: right;
}
.group-table {
  margin-top: 1.25rem;
}
.group-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem 1.5rem;
}
.group-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 22rem;
  gap: 0 2rem;
  align-items: start;
}
.group-layout > .tool-panel {
  margin-top: 2.5rem;
}
.group-layout > .tool-panel h3 {
  margin-top: 1.25rem;
}
@media (max-width: 56rem) {
  .group-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 40rem) {
  .group-table .numeric {
    text-align: left;
  }
}
.member-table select {
  font: inherit;
  max-width: 100%;
  padding: 0.25rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
}
.invite-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.invite-list li {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.75rem;
  padding: 0.375rem 0;
  border-bottom: 1px solid var(--line);
}
.invite-panel {
  max-width: 36rem;
  margin-top: 1rem;
}
.invite-panel p {
  margin: 0 0 0.75rem;
}
.account-panels .tool-panel a {
  color: var(--link);
}
.tool-panel > p.muted {
  margin: 0 0 1rem;
  font-size: 0.9375rem;
}
.import-form {
  max-width: 36rem;
  margin-top: 1.5rem;
}
.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
  align-items: center;
  margin-top: 0.5rem;
}
.flag-table .flag-actions {
  min-width: 12rem;
}
.flag-table .flag-actions > button + button {
  margin-left: 0.5rem;
}
.flag-table .dismiss {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.flag-table .error,
.import-table .error {
  margin: 0.25rem 0 0;
  color: var(--error);
}
.import-table .numeric {
  text-align: right;
}
@media (max-width: 40rem) {
  .import-table .numeric {
    text-align: left;
  }
  .flag-table .flag-actions {
    padding-top: 0.5rem;
  }
}
.suggestion-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 22rem), 1fr));
  gap: 1rem;
  margin: 0.5rem 0 0;
  padding: 0;
  list-style: none;
}
.suggestion {
  margin: 0;
  padding: 1rem 1.25rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.suggestion h2 {
  margin: 0 0 0.375rem;
  font-size: 1rem;
}
.suggestion p {
  margin: 0.25rem 0;
}
.line-add {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
  align-items: center;
  margin: 0 0 1.5rem;
}
.review-heading {
  margin: 0 0 0.5rem;
  font-size: 1rem;
}
.review-lines {
  margin: 0 0 1rem;
  padding-left: 1.5rem;
}
.review-lines li {
  margin-bottom: 0.125rem;
}
.add-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  margin-top: 1.5rem;
  padding: 1rem;
  border-radius: 8px;
  background: var(--surface);
}
.add-actions .help,
.add-actions .error {
  flex-basis: 100%;
  margin: 0;
}
.add-actions .error {
  color: var(--error);
}
/* Entering a whole book: a row per recipe (Ray's wireframe). */
.bulk-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-end;
  gap: 1rem;
}
.bulk-head h1 {
  margin: 0 0 0.25rem;
}
.bulk-head .muted a {
  color: var(--link);
}
.bulk-edition {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.875rem;
  max-width: 100%;
}
.bulk-edition select,
.bulk-row input,
.bulk-row textarea {
  font: inherit;
  padding: 0.375rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  min-width: 0;
  max-width: 100%;
  box-sizing: border-box;
}
.bulk-progress {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 2rem;
  margin: 1.25rem 0 1rem;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  background: var(--surface);
  font-size: 0.9375rem;
}
.bulk-entry .help {
  color: var(--muted);
  font-size: 0.875rem;
}
.bulk-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.bulk-grid {
  border: 1px solid var(--line);
  border-radius: 8px;
}
.bulk-title {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.bulk-row input.bulk-chapter {
  font-size: 0.875rem;
  padding: 0.25rem 0.5rem;
}
.bulk-row {
  display: grid;
  grid-template-columns: 6rem minmax(0, 1fr) minmax(0, 2fr) 10rem;
  gap: 0.5rem 0.75rem;
  align-items: start;
  padding: 0.75rem;
  border-top: 1px solid var(--line);
}
.bulk-row:first-child {
  border-top: none;
}
.bulk-row.has-checks {
  background: var(--admin-bg);
}
.bulk-row.fresh:last-child {
  background: var(--chip);
}
.bulk-labels {
  padding-top: 0.5rem;
  padding-bottom: 0.5rem;
  background: var(--surface);
  color: var(--muted);
  font-size: 0.8125rem;
  font-weight: 600;
}
.bulk-lines textarea {
  width: 100%;
  resize: vertical;
}
.bulk-summary {
  margin: 0.25rem 0 0;
  color: var(--muted);
  font-size: 0.8125rem;
}
.bulk-row.has-checks .bulk-summary,
.bulk-row.fresh:last-child .bulk-summary {
  color: var(--fg);
}
.bulk-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  list-style: none;
  padding: 0;
  margin: 0.375rem 0 0;
}
.bulk-chips li {
  margin: 0;
  padding: 0.125rem 0.5rem;
  border: 1px solid var(--line);
  border-radius: 6px;
  color: var(--fg);
  font-size: 0.8125rem;
}
.bulk-chips button.link {
  margin-left: 0.25rem;
  color: var(--fg);
  font-weight: 600;
}
.bulk-status {
  margin: 0.375rem 0 0;
  font-size: 0.875rem;
}
.bulk-status.error {
  color: var(--error);
}
.bulk-row.has-checks .bulk-status.error {
  color: var(--fg);
}
.bulk-empty {
  margin: 0;
  padding: 1rem;
}
@media (max-width: 48rem) {
  .bulk-row {
    grid-template-columns: 5rem minmax(0, 1fr);
  }
  .bulk-lines,
  .bulk-status {
    grid-column: 1 / -1;
  }
  .bulk-labels {
    display: none;
  }
  .bulk-row:nth-child(2) {
    border-top: none;
  }
}.aside-card {
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.aside-card h2 {
  margin: 0 0 0.375rem;
  font-size: 1rem;
}
.aside-card p {
  color: var(--muted);
  font-size: 0.875rem;
}
.aside-card a:not(.button-primary) {
  color: var(--link);
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
/* A suggested merge: which name to keep, one choice a line. */
.keep-name {
  border: 0;
  padding: 0;
  margin: 0.25rem 0;
}
.keep-name legend {
  padding: 0;
  font-size: 0.9em;
  color: var(--muted);
}
.keep-name label {
  display: block;
  padding: 0.2rem 0;
}
/* How sure the model says it is, as a small tag in the byline. */
.certainty {
  padding: 0.0625rem 0.375rem;
  border-radius: 4px;
  color: var(--fg);
}
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
