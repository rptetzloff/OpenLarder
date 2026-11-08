"""Looking a book up on Open Library by ISBN, edition or work.

Open Library's catalog is public domain (CC0), so what comes from it can go
into the ODbL catalog without conditions. Its API asks callers to identify
themselves with a contact address, to make requests on behalf of a person
rather than in bulk, and to cache what they get; adding a book stores the
result, which is the cache. Identified callers may make 3 requests a
second. Covers are fetched by cover ID, which is not rate-limited, rather
than by ISBN, which is limited to 100 per 5 minutes.

This returns what Open Library says. Deciding what to store is books.py's.
"""

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx2

from openlarder import isbn

BASE = "https://openlibrary.org"
COVERS = "https://covers.openlibrary.org/b/id"
USER_AGENT = "OpenLarder/0.1 (https://openlarder.com; privacy@openlarder.com)"
TIMEOUT = 10.0


class NotFound(LookupError):
    pass


class Unavailable(RuntimeError):
    """Open Library could not be reached or answered with an error."""


@dataclass
class FoundAuthor:
    open_library_id: str  # "OL7106535A"
    # As a book would print it, by clean_name.
    name: str
    kind: str = "person"


@dataclass
class FoundBook:
    isbn13: str | None  # None only for an edition without one, or a work alone
    title: str  # the work's, or the edition's when it has no work
    edition_title: str | None
    subtitle: str | None
    work_id: str | None  # "OL29227890W"
    edition_id: str  # "OL40203348M", or "" for a work alone
    publisher: str | None
    published_year: int | None
    cover_id: int | None
    authors: list[FoundAuthor] = field(default_factory=list)


COVER_SIZES = ("S", "M", "L")


def cover_url(cover_id: int, size: str = "M") -> str:
    """Where the site serves a cover: its own path, which Cloudflare caches.

    Not Open Library's address: a cover fetched from there takes 1.3-1.7 s
    through two redirects, and each visitor's browser would contact the
    Internet Archive. routers/covers.py fetches it once per Cloudflare cache.
    """
    return f"/covers/{cover_id}-{size}.jpg"


async def fetch_cover(
    cover_id: int, size: str, transport: httpx2.AsyncBaseTransport | None = None
) -> bytes:
    """The cover image from Open Library, or NotFound.

    ?default=false makes an unknown ID a 404 rather than a blank placeholder.
    By cover ID is not rate-limited, so this is not paced with the API calls.
    """
    async with httpx2.AsyncClient(
        transport=transport,
        headers={"User-Agent": USER_AGENT},
        timeout=15.0,
        follow_redirects=True,
    ) as client:
        try:
            response = await client.get(f"{COVERS}/{cover_id}-{size}.jpg?default=false")
        except httpx2.HTTPError as exc:
            raise Unavailable(f"Open Library covers could not be reached: {exc!r}") from exc
    if response.status_code == 404:
        raise NotFound(f"cover {cover_id}")
    if response.status_code >= 400 or not response.headers.get("content-type", "").startswith(
        "image/"
    ):
        raise Unavailable(f"Open Library covers answered {response.status_code} for {cover_id}")
    return response.content


def book_url(open_library_edition_id: str) -> str:
    return f"{BASE}/books/{open_library_edition_id}"


def work_url(open_library_work_id: str) -> str:
    return f"{BASE}/works/{open_library_work_id}"


def author_url(open_library_author_id: str) -> str:
    return f"{BASE}/authors/{open_library_author_id}"


def _key_id(key: str | None) -> str | None:
    """'/works/OL29227890W' -> 'OL29227890W'."""
    return key.rsplit("/", 1)[-1] if key else None


def _year(publish_date: str | None) -> int | None:
    # Open Library dates are free text: "2023", "March 7, 2023", "c1998".
    found = re.search(r"(?<!\d)(1[4-9]\d\d|2[01]\d\d)(?!\d)", publish_date or "")
    return int(found.group(1)) if found else None


# A bracketed note that says the name is an organisation's: "(Firm)".
_ORGANISATION = {
    "firm",
    "organization",
    "organisation",
    "company",
    "corporation",
    "restaurant",
    "society",
    "association",
}
# A last part that is a suffix, not a first name: "King, Martin, Jr.".
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}
# A last part that is a company's, not a first name: "Sunset Books, Inc.".
_COMPANY = {"inc", "ltd", "llc", "co"}


def clean_name(name: str) -> tuple[str, str]:
    """Open Library's catalogue form of a name, as a book would print it,
    and whether it is a person's or an organisation's.

    "Moore, Russell (Chef)" -> ("Russell Moore", "person");
    "America's Test Kitchen (Firm)" -> ("America's Test Kitchen",
    "organisation"). Bracketed notes go (roles, dates, fuller forms), and
    "Last, First" turns round, as linking.name_key reads it for matching.
    """
    notes = [n.strip().casefold().rstrip(".") for n in re.findall(r"\(([^)]*)\)", name)]
    kind = "organisation" if any(n in _ORGANISATION for n in notes) else "person"
    bare = " ".join(re.sub(r"\([^)]*\)", " ", name).split())
    parts = [p.strip() for p in bare.split(",")]
    last = parts[-1].casefold().rstrip(".") if parts else ""
    if kind == "person" and all(parts) and last not in _COMPANY:
        if len(parts) == 2:
            bare = f"{parts[1]} {parts[0]}"
        elif len(parts) == 3 and last in _SUFFIXES:
            bare = f"{parts[1]} {parts[0]} {parts[2]}"
    return bare or " ".join(name.split()), kind


def _text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


# At most one request per MIN_INTERVAL across the whole process, which keeps
# under Open Library's 3 a second for identified callers however the
# requests arrive: a bulk import adds books one after another. Tests set it
# to 0.
MIN_INTERVAL = 0.35
_pace = asyncio.Lock()
_last = 0.0


async def _wait_turn() -> None:
    global _last
    async with _pace:
        delay = _last + MIN_INTERVAL - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        _last = time.monotonic()


async def _get(client: httpx2.AsyncClient, path: str) -> dict[str, Any]:
    await _wait_turn()
    try:
        response = await client.get(BASE + path)
    except httpx2.HTTPError as exc:
        raise Unavailable(f"Open Library could not be reached: {exc!r}") from exc
    if response.status_code == 404:
        raise NotFound(path)
    if response.status_code >= 400:
        raise Unavailable(f"Open Library answered {response.status_code} for {path}")
    return response.json()


def _client(transport: httpx2.AsyncBaseTransport | None) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        transport=transport,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
    )


class BadReference(ValueError):
    pass


def parse_reference(raw: str) -> tuple[str, str]:
    """An ISBN, or an Open Library edition or work ID or link.

    Returns ("isbn", isbn13), ("edition", "OL28936410M") or ("work",
    "OL21362065W"). A link may carry a slug after the ID, as Open Library's
    own pages do.
    """
    found = re.search(r"(?<![A-Z0-9])OL[1-9][0-9]*[MW](?![A-Z0-9])", raw.strip().upper())
    if found:
        key = found.group(0)
        return ("edition" if key.endswith("M") else "work"), key
    try:
        return "isbn", isbn.normalise(raw)
    except isbn.InvalidIsbn:
        raise BadReference(
            "Give an ISBN, or an Open Library link to the book or the edition."
        ) from None


async def find_by_isbn(
    isbn13: str, transport: httpx2.AsyncBaseTransport | None = None
) -> FoundBook:
    """The edition with this ISBN, its work, and the work's authors in order."""
    async with _client(transport) as client:
        edition = await _get(client, f"/isbn/{isbn13}.json")
        return await _read(client, edition, isbn13)


async def find(
    reference: tuple[str, str], transport: httpx2.AsyncBaseTransport | None = None
) -> FoundBook:
    """What parse_reference named. A work alone has no edition: its
    edition_id is "" and its isbn13 None."""
    kind, key = reference
    if kind == "isbn":
        return await find_by_isbn(key, transport)
    async with _client(transport) as client:
        if kind == "edition":
            edition = await _get(client, f"/books/{key}.json")
            return await _read(client, edition, None)
        return await _read(client, {}, None, work_id=key)


def _edition_isbn(edition: dict[str, Any]) -> str | None:
    for raw in (edition.get("isbn_13") or []) + (edition.get("isbn_10") or []):
        try:
            return isbn.normalise(raw)
        except (isbn.InvalidIsbn, TypeError):
            continue
    return None


async def _read(
    client: httpx2.AsyncClient,
    edition: dict[str, Any],
    isbn13: str | None,
    work_id: str | None = None,
) -> FoundBook:
    work_id = work_id or _key_id((edition.get("works") or [{}])[0].get("key"))
    work = await _get(client, f"/works/{work_id}.json") if work_id else {}

    # The work's authors are the book's; an edition's list is a fallback
    # for editions not attached to a work.
    keys = [a.get("author", {}).get("key") for a in work.get("authors") or []] or [
        a.get("key") for a in edition.get("authors") or []
    ]
    authors = []
    for key in keys:
        author_id = _key_id(key)
        if not author_id or any(a.open_library_id == author_id for a in authors):
            continue
        record = await _get(client, f"/authors/{author_id}.json")
        if name := _text(record.get("name")):
            authors.append(FoundAuthor(author_id, *clean_name(name)))

    title = _text(work.get("title")) or _text(edition.get("title"))
    if not title:
        raise NotFound(f"{work_id or isbn13} has no title")
    publishers = edition.get("publishers") or []
    covers = [c for c in (edition.get("covers") or work.get("covers") or []) if c and c > 0]
    return FoundBook(
        isbn13=isbn13 or _edition_isbn(edition),
        title=title,
        edition_title=_text(edition.get("title")),
        subtitle=_text(work.get("subtitle")) or _text(edition.get("subtitle")),
        work_id=work_id,
        edition_id=_key_id(edition.get("key")) or "",
        # The first listed. Open Library sometimes lists one publisher in
        # several forms; which reads best is not something to guess at here.
        publisher=_text(publishers[0]) if publishers else None,
        published_year=_year(edition.get("publish_date")),
        cover_id=covers[0] if covers else None,
        authors=authors,
    )
