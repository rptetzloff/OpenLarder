"""Search engines' crawlers, verified, so the rate limit leaves them alone.

Google renders the site's pages as a browser would, and the pages' own
requests to /api come from its crawler's addresses without the header a
browser marks them with (ratelimit.py): counted as a program, and once over
the limit refused, which would index the pages empty. *Ray, 2026-11-10,
seeing 66.249.x.x, Google's, on API usage.*

A crawler is known by its User-Agent, which anyone can copy, so it's
believed only as the engines say to check: the address is in the ranges
the engine publishes, fetched a day at a time; or, when they couldn't be
fetched, the address's reverse DNS name is theirs and that name's forward
lookup gives the address back. Docker's DNS doesn't answer reverse lookups,
so the published ranges are what works in the container. Answers are kept
a day per address.
"""

import asyncio
import ipaddress
import logging
import re
import socket
import time

import httpx2

log = logging.getLogger(__name__)

# Name -> (User-Agent pattern, the host names its addresses reverse to).
CRAWLERS = {
    "googlebot": (
        re.compile(r"Googlebot|Google-InspectionTool|GoogleOther|Storebot-Google", re.I),
        (".googlebot.com", ".google.com"),
    ),
    "bingbot": (re.compile(r"bingbot|BingPreview|msnbot", re.I), (".search.msn.com",)),
    "applebot": (re.compile(r"Applebot", re.I), (".applebot.apple.com",)),
}
LABELS = {"googlebot": "Googlebot", "bingbot": "Bingbot", "applebot": "Applebot"}
# The address ranges each engine publishes for its crawler.
RANGES = {
    "googlebot": "https://developers.google.com/static/crawling/ipranges/common-crawlers.json",
    "bingbot": "https://www.bing.com/toolbox/bingbot.json",
    "applebot": "https://search.developer.apple.com/applebot.json",
}
USER_AGENT = "OpenLarder/0.1 (https://openlarder.com; privacy@openlarder.com)"
_ranges: dict[str, list] = {}
_ranges_at = 0.0
_refreshing: asyncio.Task | None = None
KEEP = 24 * 3600
LOOKUP_TIMEOUT = 2.0
# Address -> (crawler name or "", when checked).
_checked: dict[str, tuple[str, float]] = {}


def reset() -> None:
    global _ranges_at
    _checked.clear()
    _ranges.clear()
    _ranges_at = 0.0


def set_ranges(found: dict[str, list[str]]) -> None:
    """The engines' ranges, as their lists give them (tests, and refresh)."""
    global _ranges_at
    _ranges.clear()
    for name, prefixes in found.items():
        _ranges[name] = [ipaddress.ip_network(p, strict=False) for p in prefixes]
    _ranges_at = time.monotonic()
    _checked.clear()


async def refresh(transport: httpx2.AsyncBaseTransport | None = None) -> None:
    """Fetch every engine's ranges; a list that fails keeps what was had."""
    found = {name: [str(n) for n in nets] for name, nets in _ranges.items()}
    async with httpx2.AsyncClient(
        transport=transport,
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for name, url in RANGES.items():
            try:
                response = await client.get(url)
                response.raise_for_status()
                found[name] = [
                    p.get("ipv4Prefix") or p.get("ipv6Prefix")
                    for p in response.json()["prefixes"]
                    if p.get("ipv4Prefix") or p.get("ipv6Prefix")
                ]
            except (httpx2.HTTPError, ValueError, KeyError) as exc:
                log.warning("Couldn't fetch %s's address ranges: %s", name, exc)
    set_ranges(found)


def _in_ranges(name: str, address: str) -> bool | None:
    """Whether the address is in the engine's ranges; None without them."""
    nets = _ranges.get(name)
    if not nets:
        return None
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in net for net in nets)


def claimed(user_agent: str) -> str | None:
    """The crawler the User-Agent says it is, unchecked."""
    for name, (pattern, _) in CRAWLERS.items():
        if pattern.search(user_agent or ""):
            return name
    return None


def _confirm(address: str, suffixes: tuple[str, ...]) -> bool:
    try:
        host = socket.gethostbyaddr(address)[0].lower().rstrip(".")
    except OSError:
        return False
    if not host.endswith(suffixes):
        return False
    try:
        return address in socket.gethostbyname_ex(host)[2]
    except OSError:
        return False


async def verified(user_agent: str, address: str) -> str | None:
    """The crawler, if the User-Agent claims one and its address proves it."""
    name = claimed(user_agent)
    if name is None:
        return None
    global _refreshing
    now = time.monotonic()
    if now - _ranges_at > KEEP and (_refreshing is None or _refreshing.done()):
        # In the background; this request goes by what's known now.
        _refreshing = asyncio.get_running_loop().create_task(refresh())
    if (kept := _checked.get(address)) and now - kept[1] < KEEP:
        return kept[0] or None
    ok = _in_ranges(name, address)
    if ok is None:
        try:
            ok = await asyncio.wait_for(
                asyncio.to_thread(_confirm, address, CRAWLERS[name][1]), LOOKUP_TIMEOUT
            )
        except TimeoutError:
            # Asked again next time, rather than kept as a no.
            return None
    if len(_checked) > 10_000:
        _checked.clear()
    _checked[address] = (name if ok else "", now)
    return name if ok else None
