// Signing in is a full page load to the broker and back (routers/auth.py),
// and comes back to the page it began on: every sign-in link says which.

// The page "Sign-in didn't work" is shown on. Its own links try again for
// the page the failed try was coming back to, which the server still has.
const FAILED = "/sign-in-failed";

// Made when it's used, not when the page is drawn: the lists rewrite their
// address as someone types in them.
export function signInHref(): string {
  if (location.pathname.replace(/\/+$/, "") === FAILED) return "/api/auth/login?again=true";
  return "/api/auth/login?next=" + encodeURIComponent(location.pathname + location.search);
}
