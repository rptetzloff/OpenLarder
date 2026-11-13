<script setup lang="ts">
// The content rules here are SCOPING.md's, in plain words. SCOPING says
// they and the allergen wording are reviewed by a lawyer; until then this is
// an accurate account of how the site works, not legal advice.
import { onMounted, ref } from "vue";
import { type Agreement, readAgreement } from "../review";

document.title = "Terms of service · OpenLarder";

// The agreement's wording is the server's (agreement.py), so it's shown as
// what was actually accepted.
const agreement = ref<Agreement | null>(null);
onMounted(async () => {
  // A link to a section ("How this works" goes to #commissions): the page
  // is drawn after the browser looked for it, so go there now.
  if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  agreement.value = await readAgreement().catch(() => null);
});
</script>

<template>
  <article>
    <h1>Terms of service</h1>
    <p class="updated">Last updated November 11, 2026</p>

    <p>
      OpenLarder is a free, open index of the recipes in cookbooks: which book, which page, and
      what goes in them. It is run by Ray Tetzloff as an individual in Wisconsin, USA. By using the
      site you agree to these terms. Questions go to
      <a href="mailto:privacy@openlarder.com">privacy@openlarder.com</a>.
    </p>

    <h2>What OpenLarder is, and is not</h2>
    <p>
      OpenLarder records facts about recipes: their titles, the pages they are on, their
      ingredients and how they are tagged. It never reproduces a book's instructions, headnotes or
      other text. To cook a recipe, you need the book.
    </p>

    <h2>Accounts</h2>
    <p>
      You sign in through Google, GitHub or your email address. Keep access to your sign-in
      method to yourself; what is done with your account is your responsibility. Accounts may be
      suspended for breaking these terms.
    </p>

    <h2>Contributing</h2>
    <p>
      Contributors, whom a moderator names, add books and their recipes. What they add waits for a
      moderator's review, seen only by them and the moderators until it's approved, and may be
      sent back with what to fix, until they become trusted contributors, whose additions publish
      at once and can still be changed or undone. Everyone who adds to the catalog first accepts the contributor
      agreement below, and accepts it again if it changes. These rules apply too.
    </p>
    <ul>
      <li>
        <strong>Facts, not copied text.</strong> Contribute titles, page numbers, ingredient lines
        and tags. Don't paste a book's instructions, headnotes or other text, and don't upload
        scans or photos of its pages.
      </li>
      <li>
        <strong>Catalog contributions are open data.</strong> Books, recipes, page numbers and
        ingredients you add or correct are published under the
        <a href="https://opendatacommons.org/licenses/odbl/1-0/">Open Database License (ODbL)</a>,
        so anyone may reuse them on the same terms. You agree to that before your first
        contribution.
      </li>
      <li>
        <strong>Everything is versioned.</strong> Contributions are public, attributed to your
        display name in the edit history, and may be reviewed, corrected, reverted or removed.
      </li>
    </ul>

    <h3>The contributor agreement</h3>
    <p v-if="!agreement" class="status">Loading…</p>
    <ol v-else class="agreement-points">
      <li v-for="(point, i) in agreement.points" :key="i">{{ point }}</li>
    </ol>

    <h2>Family collections</h2>
    <p>
      Anyone signed in can add family collections of their own now. The same rule holds: titles
      and ingredient names, never amounts or the method. A private collection is not part of the
      catalog: it is not published, licensed or shown to anyone else, and you can delete it at
      any time. A collection made public becomes catalog data under the rules above.
    </p>

    <h2>Allergens and diets</h2>
    <p>
      Allergen, meat, alcohol and diet information comes from public food databases and from contributors. It
      describes an ingredient in general, not any product: one brand's stock may contain milk when
      another's doesn't, and oats may be processed alongside wheat. It may be incomplete or wrong.
      OpenLarder never says a recipe is safe for an allergy. Always check the labels of what you
      buy, and ask a doctor about medical needs.
    </p>

    <h2 id="commissions">Buy and shop links</h2>
    <p>
      Links to buy a book, and an ingredient's Shop link, go to shops OpenLarder is an affiliate
      of: a bookshop, or a grocer you choose. If you buy something after following one,
      OpenLarder may earn a commission from the shop, at no cost to you. The links are made from
      the book's ISBN or the ingredient's name: no shop pays to be listed, and nothing in the
      catalog is there because of a commission. As an Amazon Associate, OpenLarder earns from
      qualifying purchases. What a link counts is in the
      <a href="/privacy">privacy policy</a>.
    </p>

    <h2>Copyright</h2>
    <p>
      If you believe something on OpenLarder copies your work, email
      <a href="mailto:privacy@openlarder.com">privacy@openlarder.com</a> with the page and what it
      copies, and it will be looked at promptly.
    </p>

    <h2>No warranty</h2>
    <p>
      OpenLarder is provided as it is, free of charge, without warranties of any kind, including
      that it is accurate, complete or available. To the fullest extent the law allows, its
      operator is not liable for any loss or harm arising from using it, including from relying
      on recipe, ingredient, allergen or diet information.
    </p>

    <h2>Changes and law</h2>
    <p>
      These terms may change; the date at the top changes with them, and the full history is
      public in
      <a href="https://github.com/rptetzloff/OpenLarder">OpenLarder's source repository</a>.
      They are governed by the laws of the State of Wisconsin, USA.
    </p>
  </article>
</template>
