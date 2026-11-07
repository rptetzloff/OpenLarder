<script setup lang="ts">
// Written from what the code does, not from a template. When what is
// stored, who processes it, or which cookies are set changes, this page
// changes in the same pull request.
document.title = "Privacy policy · OpenLarder";
</script>

<template>
  <article>
    <h1>Privacy policy</h1>
    <p class="updated">Last updated 7 November 2026</p>

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
      <li>your display name, as Authgear provides it, refreshed each time you sign in;</li>
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

    <h2>Contributions</h2>
    <p>
      Contributing to the catalog is not open yet. When it is, contributions will be public and
      attributed to your display name in the edit history, and this page will say so in more
      detail before that happens.
    </p>

    <h2>Your choices</h2>
    <p>
      You can sign out at any time, which ends the session here and at Authgear. To see what
      OpenLarder holds about you, correct it, or delete your account, email
      <a href="mailto:privacy@openlarder.com">privacy@openlarder.com</a>. Deleting your account
      removes your user record and sessions here; your Authgear account can be removed at the
      same time on request.
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
