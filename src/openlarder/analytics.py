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

A sign-in is counted too (*Ray's round 2 spec, 2026-11-13*), as an event
named "sign-in" saying whether the account is new or returning. Someone
returning lands on the page they began on, so no page view says they signed
in; the callback (routers/auth.py) marks the address it sends them to,
"#signed-in=returning", and the loader takes the mark off the address
before the page is drawn and, after the page view, sends the event. For a
browser that asks not to be tracked the mark is taken off and nothing is
sent.

The spec had a one-minute cookie carry the word. SCOPING.md brings a
consent banner with anything that sets a cookie for analytics, and the
privacy page says there are none, so *Ray, 2026-11-13*, chose the mark:
nothing is kept in the browser. What it costs: a link passed round with
the mark on it counts a sign-in that didn't happen. Anyone can already
post a false count to the collector, so the number was never proof.

The event is sent the way the page view is, as a function, because Umami's
track("name", data) adds the page's whole address, search words and all,
and its title (read in the tracker the site loads, 2026-11-13). It says
what a page view says less the page: the address is a fixed "/" and the
referrer is empty. A fixed "/" rather than none: every payload sent so far
has had an address, and what Umami's collector does without one isn't
checked.
"""

import json

from openlarder.config import Settings

LOADER = """<script>
(function () {
  var mark = location.hash.match(/^#@@MARK@@=(new|returning)$/);
  if (mark) history.replaceState(history.state, "", location.pathname + location.search);
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
    var viewed = window.umami.track(function (props) {
      props.url = path;
      props.title = "";
      props.referrer = from;
      return props;
    });
    if (!mark) return;
    Promise.resolve(viewed).then(function () {
      window.umami.track(function (props) {
        props.url = "/";
        props.title = "";
        props.referrer = "";
        props.name = "sign-in";
        props.data = { account: mark[1] };
        return props;
      });
    });
  };
  document.head.appendChild(s);
})();
</script>"""


# What the sign-in callback puts after the address for the loader.
SIGNED_IN_MARK = "signed-in"


def signed_in_mark(*, new: bool) -> str:
    """The end of the address a sign-in is sent to, for the loader to count."""
    return f"#{SIGNED_IN_MARK}={'new' if new else 'returning'}"


def counting(settings: Settings) -> bool:
    """Whether anything is counted: Umami's settings are both there."""
    return bool(settings.umami_script_url and settings.umami_website_id)


def _js(value: str) -> str:
    """A string as a JavaScript literal that can't close the <script>."""
    return json.dumps(value).replace("<", "\\u003c")


def loader(settings: Settings) -> str:
    """The tag for every page's head, or nothing without Umami's settings."""
    if not counting(settings):
        return ""
    assert settings.umami_script_url and settings.umami_website_id
    return (
        LOADER.replace("@@SITE@@", _js(settings.umami_website_id))
        .replace("@@SRC@@", _js(settings.umami_script_url))
        .replace("@@MARK@@", SIGNED_IN_MARK)
    )
