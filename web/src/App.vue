<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import NameForm from "./components/NameForm.vue";
import type { Me } from "./me";
import AccountPage from "./pages/AccountPage.vue";
import AdminImportPage from "./pages/AdminImportPage.vue";
import AdminImportsPage from "./pages/AdminImportsPage.vue";
import AdminPage from "./pages/AdminPage.vue";
import FlagsPage from "./pages/FlagsPage.vue";
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
const path = location.pathname.replace(/\/+$/, "");
const page = pages[path];
const onAccount = path === "/account";
const onBooks = path === "/books";
const onIngredients = path === "/ingredients";
const onSearch = path === "/search";
const onAdmin = path === "/admin";
const onImport = path === "/admin/import";
const onImports = path === "/admin/imports";
const flagScope = ({ "/admin/flags": "all", "/account/flags": "mine" } as const)[path];
const UUID = "([0-9a-f-]{36})";
const match = (pattern: string) => path.match(new RegExp(`^${pattern}$`, "i"))?.[1] ?? null;
const bookId = match(`/books/${UUID}`);
const newRecipeFor = match(`/books/${UUID}/recipes/new`);
const editBookId = match(`/books/${UUID}/edit`);
const recipeId = match(`/recipes/${UUID}`);
const ingredientId = match(`/ingredients/${UUID}`);
const editRecipeId = match(`/recipes/${UUID}/edit`);

// A placeholder until there is a catalog to show: proves the SPA reaches the
// API through whichever path it is served from, and that sign-in works.
const status = ref("checking…");
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
    const res = await fetch("/readyz");
    const body = await res.json();
    status.value = res.ok ? `database ${body.database}, schema ${body.revision}` : body.database;
  } catch {
    status.value = "API unreachable";
  }
  try {
    const res = await fetch("/api/auth/me");
    user.value = res.ok ? await res.json() : null;
  } catch {
    user.value = null;
  }
});
</script>

<template>
  <header>
    <a href="/books">Books</a>
    <a href="/ingredients">Ingredients</a>
    <a href="/search" class="nav">Search</a>
    <template v-if="user">
      <a v-if="user.is_admin" href="/admin">Admin</a>
      <a href="/account">{{ user.display_name ?? "Choose a name" }}</a>
      <!-- A form, not fetch: signing out ends at the broker, which ends the
           session there and sends the browser back here. -->
      <form method="post" action="/api/auth/logout">
        <button type="submit">Sign out</button>
      </form>
    </template>
    <!-- A full page load, not fetch: the broker's sign-in page is a redirect. -->
    <a v-else-if="user === null" href="/api/auth/login">Sign in</a>
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
    <IngredientPage v-else-if="ingredientId" :id="ingredientId" :user="user" />
    <AdminPage v-else-if="onAdmin" :user="user" />
    <AdminImportPage v-else-if="onImport" :user="user" />
    <AdminImportsPage v-else-if="onImports" :user="user" />
    <FlagsPage v-else-if="flagScope" :user="user" :scope="flagScope" />
    <BookPage v-else-if="bookId" :id="bookId" :user="user" />
    <RecipeFormPage v-else-if="newRecipeFor" :book-id="newRecipeFor" />
    <BookEditPage v-else-if="editBookId" :id="editBookId" />
    <RecipeFormPage v-else-if="editRecipeId" :recipe-id="editRecipeId" />
    <RecipePage v-else-if="recipeId" :id="recipeId" :user="user" />
    <template v-else>
      <h1>OpenLarder</h1>
      <p>A free, open index of the recipes in your cookbooks.</p>
      <p><a href="/books">Browse the books</a></p>
      <p v-if="signInFailed" role="alert">Sign-in didn't work. Please try again.</p>
      <p class="status">{{ status }}</p>
    </template>
  </main>
  <footer>
    <a href="/">OpenLarder</a>
    <a href="/privacy">Privacy</a>
    <a href="/terms">Terms</a>
  </footer>
</template>

<style>
:root {
  --bg: #fbfaf7;
  --fg: #1f1e1c;
  --muted: #5f5e5a;
  --accent: #8a5a1c;
  --accent-hover: #734a15;
  --on-accent: #ffffff;
  --border: #8a877f;
  --error: #b3261e;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1a1918;
    --fg: #ecebe6;
    --muted: #a8a59c;
    /* The logo's amber, with dark text: white on it is 2.2:1. */
    --accent: #e0a24a;
    --accent-hover: #ebb368;
    --on-accent: #1f1e1c;
    --border: #77746c;
    --error: #f2a8a2;
  }
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: system-ui, sans-serif;
}
header {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 0.75rem;
  max-width: 40rem;
  margin: 0 auto;
  padding: 1rem 1rem 0;
  font-size: 0.875rem;
}
header form {
  margin: 0;
}
header .nav {
  margin-right: auto;
}
header a,
header button,
footer a {
  color: var(--fg);
  text-decoration: underline;
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  cursor: pointer;
}
main {
  max-width: 40rem;
  margin: 0 auto;
  padding: 2rem 1rem 3rem;
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
.ol-link .error {
  color: var(--error);
}
.recipe-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-width: 32rem;
}
.recipe-form > label {
  font-weight: 600;
  margin-top: 0.75rem;
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
.search-book button {
  margin-left: 0.5rem;
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
footer {
  display: flex;
  gap: 1rem;
  max-width: 40rem;
  margin: 0 auto;
  padding: 0 1rem 2rem;
  font-size: 0.875rem;
}
</style>
