"""Web addresses for website sources: checking one, and the site it's on.

A website source is one site, found by its host without "www."
("smittenkitchen.com"); each recipe on it is a page, by its address.
Nothing here fetches a page: OpenLarder links to recipes, it doesn't copy
them (the content rules), and an address typed by someone is not one the
server should go and visit.
"""

from urllib.parse import urlsplit, urlunsplit

MAX_URL = 2000


class BadAddress(ValueError):
    """The reason is written to be shown beside the form."""


def page(address: str) -> tuple[str, str]:
    """An address as stored, and its site's host: whitespace and any
    "#section" dropped, scheme and host in lower case.

    "https://www.SmittenKitchen.com/2024/rhubarb/#recipe" ->
    ("https://www.smittenkitchen.com/2024/rhubarb/", "smittenkitchen.com").
    """
    address = address.strip()
    if len(address) > MAX_URL:
        raise BadAddress(f"A web address is at most {MAX_URL} characters.")
    parts = urlsplit(address)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise BadAddress(
            "A web address starts http:// or https://, like https://example.com/rhubarb."
        )
    netloc = parts.hostname.lower() + (f":{parts.port}" if parts.port else "")
    url = urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))
    return url, site(parts.hostname)


def site(host_or_address: str) -> str:
    """A site's host, as a website source records it: lower case, without
    "www.", from a host or a whole address."""
    value = host_or_address.strip()
    host = urlsplit(value).hostname if "://" in value else value
    host = (host or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host or " " in host:
        raise BadAddress("That isn't a website's address.")
    return host
