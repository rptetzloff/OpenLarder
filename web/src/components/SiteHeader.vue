<script setup lang="ts">
import { computed } from "vue";
import type { Me } from "../me";
import HeaderMenu from "./HeaderMenu.vue";

// The site's header (Ray's cleanup pass, section 3, 2026-11-11): the logo
// and four sections; signed in, two menus, "My kitchen" and the account.
// On a phone, the logo, Search and one Menu with everything in it.
// Requests is in the footer: it doesn't need to be prominent.
const props = defineProps<{
  // undefined while asking, null when signed out.
  user: Me | null | undefined;
  // The page's path, to mark where you are.
  path: string;
}>();

const SECTIONS = [
  { href: "/search", label: "Search" },
  { href: "/sources", label: "Sources" },
  { href: "/ingredients", label: "Ingredients" },
  { href: "/authors", label: "Authors" },
];
const KITCHEN = [
  { href: "/larder", label: "Larder" },
  { href: "/shelf", label: "Shelf" },
  { href: "/saved", label: "Saved" },
  { href: "/groups", label: "Groups" },
];
const account = computed(() => [
  { href: "/account", label: "Account" },
  ...(props.user?.may_edit ? [{ href: "/admin", label: "Admin" }] : []),
]);
const here = (href: string) =>
  props.path === href || props.path.startsWith(`${href}/`) ? "page" : undefined;
const name = computed(() => props.user?.display_name ?? "Account");
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

      <!-- Wider than a phone: the sections, then the menus. -->
      <nav class="sections wide-only" aria-label="Main">
        <a v-for="s in SECTIONS" :key="s.href" :href="s.href" :aria-current="here(s.href)">{{
          s.label
        }}</a>
      </nav>
      <div class="menus wide-only">
        <template v-if="user">
          <HeaderMenu id="kitchen-menu" label="My kitchen" outlined>
            <ul>
              <li v-for="k in KITCHEN" :key="k.href">
                <a :href="k.href" :aria-current="here(k.href)">{{ k.label }}</a>
              </li>
            </ul>
          </HeaderMenu>
          <HeaderMenu id="account-menu" :label="name">
            <ul>
              <li v-for="a in account" :key="a.href">
                <a :href="a.href" :aria-current="here(a.href)">{{ a.label }}</a>
              </li>
              <li>
                <!-- A form, not fetch: signing out ends at the broker, which
                     ends the session there and sends the browser back here. -->
                <form method="post" action="/api/auth/logout">
                  <button type="submit">Sign out</button>
                </form>
              </li>
            </ul>
          </HeaderMenu>
        </template>
        <!-- A full page load, not fetch: the broker's sign-in page is a redirect. -->
        <a v-else-if="user === null" href="/api/auth/login" class="secondary">Sign in</a>
      </div>

      <!-- A phone: Search, and one menu with the rest. -->
      <div class="menus phone-only">
        <a href="/search" class="search-link" :aria-current="here('/search')">Search</a>
        <HeaderMenu id="phone-menu" label="Menu" outlined full>
          <nav aria-label="Main">
            <ul>
              <li v-for="s in SECTIONS" :key="s.href">
                <a :href="s.href" :aria-current="here(s.href)">{{ s.label }}</a>
              </li>
            </ul>
          </nav>
          <template v-if="user">
            <h2 id="phone-kitchen">My kitchen</h2>
            <ul aria-labelledby="phone-kitchen">
              <li v-for="k in KITCHEN" :key="k.href">
                <a :href="k.href" :aria-current="here(k.href)">{{ k.label }}</a>
              </li>
            </ul>
            <h2 id="phone-account">{{ name }}</h2>
            <ul aria-labelledby="phone-account">
              <li v-for="a in account" :key="a.href">
                <a :href="a.href" :aria-current="here(a.href)">{{ a.label }}</a>
              </li>
              <li>
                <form method="post" action="/api/auth/logout">
                  <button type="submit">Sign out</button>
                </form>
              </li>
            </ul>
          </template>
          <ul v-else-if="user === null">
            <li><a href="/api/auth/login">Sign in</a></li>
          </ul>
        </HeaderMenu>
      </div>
    </div>
  </header>
</template>

<style scoped>
.site-header {
  border-bottom: 1px solid var(--line);
}
.bar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.5rem 1.75rem;
  max-width: var(--page);
  margin: 0 auto;
  padding: 0.75rem 1.5rem;
}
.brand img {
  display: block;
  height: 2.75rem;
  width: auto;
}
.sections {
  display: flex;
  gap: 0 1.25rem;
}
.sections a,
.search-link {
  display: inline-flex;
  align-items: center;
  min-height: 2.75rem;
  color: var(--fg);
  font-weight: 500;
  text-decoration: none;
}
.sections a:hover,
.search-link:hover {
  text-decoration: underline;
}
.sections a[aria-current="page"],
.search-link[aria-current="page"] {
  font-weight: 700;
}
.menus {
  display: flex;
  align-items: center;
  gap: 0.25rem 0.5rem;
  margin-left: auto;
}
.phone-only {
  display: none;
}
@media (max-width: 40rem) {
  .bar {
    padding: 0.5rem 1rem;
  }
  .brand img {
    height: 2.25rem;
  }
  .wide-only {
    display: none;
  }
  .phone-only {
    display: flex;
    gap: 0.25rem 1rem;
  }
}
</style>
