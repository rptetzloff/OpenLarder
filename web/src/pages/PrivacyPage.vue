<script setup lang="ts">
// Written from what the code does, not from a template. When what is
// stored, who processes it, or which cookies are set changes, this page
// changes in the same pull request.
document.title = "Privacy policy · OpenLarder";
</script>

<template>
  <article>
    <h1>Privacy policy</h1>
    <p class="updated">Last updated 9 November 2026</p>

    <p>
      OpenLarder is a free, open index of the recipes in cookbooks, run by Ray Tetzloff as an
      individual in Wisconsin, USA. This page says what personal information OpenLarder holds,
      why, and who else handles it. Questions go to
      <a href="mailto:privacy@openlarder.com">privacy@openlarder.com</a>.
    </p>

    <h2>Browsing</h2>
    <p>
      You can read the catalog without an account. OpenLarder has no advertising, no analytics
      and no tracking scripts, and it does not sell or share personal information.
    </p>
    <p>
      The site is served through Cloudflare, which sees each visitor's IP address and request in
      order to deliver the site and block attacks. See
      <a href="https://www.cloudflare.com/privacypolicy/">Cloudflare's privacy policy</a>. The
      server keeps ordinary logs of requests for troubleshooting and security. They are not used
      to build profiles of anyone.
    </p>
    <p>
      Programs reading OpenLarder's public API are limited in how often they may ask, and their
      use is recorded so that misuse can be seen and stopped. A program is counted by its API key,
      or, without one, by a name made from its IP address with a secret key (the same each day,
      but not something the address can be worked out from) and its network (the address with its
      last part removed). The IP address itself is not stored. What's kept is how many requests
      each made each day and when it was last seen, for 30 days. An API key belongs to the account
      that made it, which can see when the key was last used and revoke it. The site's own pages
      aren't counted.
    </p>
    <p>
      Book covers come from <a href="https://openlibrary.org">Open Library</a>, run by the
      Internet Archive. OpenLarder fetches each one and serves it itself, so your browser
      doesn't contact Open Library to show a cover.
    </p>
    <p>
      A book's page can have links to buy it from bookshops such as Bookshop.org, Barnes &amp;
      Noble, ThriftBooks, Book Outlet, Amazon and Kobo. OpenLarder earns a commission on what's
      bought through them. A buy link goes through OpenLarder
      first, which counts the click: which book, which shop, when, and which OpenLarder page it
      was on. It records nothing about who clicked: no account, IP address or cookie. The shop
      then sees your visit as anyone's would, and tracks the purchase under its own privacy
      policy.
    </p>
    <p>
      You can choose which shops show and in what order. Signed in, that choice is kept with your
      account. Signed out, your browser keeps it in its own storage, not in a cookie, and it is
      never sent to OpenLarder.
    </p>

    <h2>Accounts</h2>
    <p>
      Signing in is handled by <a href="https://www.authgear.com/">Authgear</a>, which holds your
      email address and, depending on how you sign in, your link to Google or GitHub and your
      passkeys. It sends sign-in emails. Authgear's handling of that information is covered by
      <a href="https://www.authgear.com/data-privacy/">its privacy policy</a>.
    </p>
    <p>OpenLarder itself stores only:</p>
    <ul>
      <li>
        the identifier Authgear gives your account, which is how OpenLarder recognises you;
      </li>
      <li>whether your account is an admin's;</li>
      <li>
        the family collections you add: each one's name, whether it is private, when you ticked
        that you understand what is kept, and each of its recipes' titles and ingredient names,
        never amounts or the method. A private collection is shown to no one but you and the
        groups you share it with, admins included; the people who run the site can reach
        anything stored on it, as on any website;
      </li>
      <li>
        the groups you are in and your role in each, which collections are shared with them, and
        for each invite link, a scrambled (hashed) copy of it, its role, when it expires, who
        made it and who used it. A group's members see each other's display names and roles;
      </li>
      <li>
        which account added each recipe, so that its flags can be shown to you, who dealt with
        a flag, and, for admins, which account ran each bulk import;
      </li>
      <li>
        the display name you choose, which is public: it is shown beside anything you add to
        the catalog;
      </li>
      <li>
        until you choose one, the name Google, GitHub or Authgear has for you, used only to
        suggest a display name and deleted once you have chosen;
      </li>
      <li>
        for each signed-in browser, a scrambled (hashed) copy of the session token, when the
        session started and when it ends, and the sign-in token Authgear issued, which is needed
        to sign you out of Authgear as well.
      </li>
    </ul>
    <p>OpenLarder does not store your email address or any password.</p>

    <h2>Cookies</h2>
    <ul>
      <li>
        <code>openlarder_session</code> keeps you signed in, for up to 30 days or until you sign
        out.
      </li>
      <li>
        <code>openlarder_sign_in</code> exists only while you are signing in, for at most an hour,
        and protects the sign-in from being forged.
      </li>
    </ul>
    <p>
      Authgear sets its own cookies on its sign-in pages, and Cloudflare may set a security
      cookie. OpenLarder sets no cookies for advertising or analytics.
    </p>
    <p>
      Your browser also keeps two things for this site, which are never sent to OpenLarder: the
      theme you choose (light or dark), and, while you sign in from an invite link, that link, so
      you come back to it.
    </p>

    <h2>Contributions</h2>
    <p>
      Contributing to the catalog is not open yet. When it is, contributions will be public and
      attributed to your display name in the edit history, and this page will say so in more
      detail before that happens. Family collections are the exception: anyone signed in can add
      their own now, and they stay private.
    </p>

    <h2>Your choices</h2>
    <p>
      You can sign out at any time, which ends the session here and at Authgear. To see what
      OpenLarder holds about you, correct it, or delete your account, email
      <a href="mailto:privacy@openlarder.com">privacy@openlarder.com</a>. Deleting your account
      removes your user record, your sessions, your group memberships and your family
      collections here; your Authgear
      account can be removed at the same time on request. You can delete a family collection
      yourself, from its page, at any time.
    </p>

    <h2>Children</h2>
    <p>OpenLarder is not directed at children under 13 and does not knowingly hold their data.</p>

    <h2>Changes</h2>
    <p>
      When this policy changes, the date at the top changes with it. The full history of this
      page is public in
      <a href="https://github.com/rptetzloff/OpenLarder">OpenLarder's source repository</a>.
    </p>
  </article>
</template>
