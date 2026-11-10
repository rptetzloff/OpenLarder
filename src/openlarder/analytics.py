"""Page-view counts with Umami, self-hosted. *Ray, 2026-11-10.*

Umami sets no cookies and keeps no IP address. Ray's calls on top of that:

- A browser that asks not to be tracked (Do Not Track, or Global Privacy
  Control) isn't: the loader below doesn't fetch Umami's script at all, so
  nothing is sent. data-do-not-track is set too, as a second guard.
- A page view says the path only: no query string, so no search words, and
  an invite link (/invite/<secret>) as plain /invite, so no secret leaves.

Two more, Claude's, for the same reasons: the page title isn't sent, since
a private family collection's name is in its page's title; and the
referrer is cut to the referring site's address, since an address can carry
a secret too.

So page views are sent by hand (data-auto-track="false"): once a page has
loaded, with what's said above and nothing else. The site's pages are full
page loads, so one view per load is every view.
"""

import json

from openlarder.config import Settings

LOADER = """<script>
(function () {
  var n = navigator;
  if (n.globalPrivacyControl === true || n.doNotTrack === "1" || window.doNotTrack === "1") return;
  var s = document.createElement("script");
  s.defer = true;
  s.src = @@SRC@@;
  s.setAttribute("data-website-id", @@SITE@@);
  s.setAttribute("data-auto-track", "false");
  s.setAttribute("data-do-not-track", "true");
  s.onload = function () {
    if (!window.umami) return;
    var path = location.pathname.replace(/^[/]invite[/].*/, "/invite") || "/";
    var from = "";
    try {
      if (document.referrer) {
        var r = new URL(document.referrer);
        if (r.origin !== location.origin) from = r.origin + "/";
      }
    } catch (e) {}
    window.umami.track(function (props) {
      props.url = path;
      props.title = "";
      props.referrer = from;
      return props;
    });
  };
  document.head.appendChild(s);
})();
</script>"""


def _js(value: str) -> str:
    """A string as a JavaScript literal that can't close the <script>."""
    return json.dumps(value).replace("<", "\\u003c")


def loader(settings: Settings) -> str:
    """The tag for every page's head, or nothing without Umami's settings."""
    if not (settings.umami_script_url and settings.umami_website_id):
        return ""
    return LOADER.replace("@@SITE@@", _js(settings.umami_website_id)).replace(
        "@@SRC@@", _js(settings.umami_script_url)
    )
