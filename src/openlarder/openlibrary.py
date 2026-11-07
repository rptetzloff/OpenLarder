"""Looking a book up on Open Library by ISBN.

Open Library's catalog is public domain (CC0), so what comes from it can go
into the ODbL catalog without conditions. Its API asks callers to identify
themselves with a contact address, to make requests on behalf of a person
rather than in bulk, and to cache what they get; adding a book stores the
result, which is the cache. Identified callers may make 3 requests a
second. Covers are fetched by cover ID, which is not rate-limited, rather
than by ISBN, which is limited to 100 per 5 minutes.

This returns what Open Library says. Deciding what to store is books.py's.
"""

import re
from dataclasses import dataclass, field
from typing import Any

import httpx2

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
    name: str


@dataclass
class FoundBook:
    isbn13: str
    title: str  # the work's, or the edition's when it has no work
    edition_title: str | None
    subtitle: str | None
    work_id: str | None  # "OL29227890W"
    edition_id: str  # "OL40203348M"
    publisher: str | None
    published_year: int | None
    cover_id: int | None
    authors: list[FoundAuthor] = field(default_factory=list)


def cover_url(cover_id: int, size: str = "M") -> str:
    return f"{COVERS}/{cover_id}-{size}.jpg"


def book_url(open_library_edition_id: str) -> str:
    return f"{BASE}/books/{open_library_edition_id}"


def _key_id(key: str | None) -> str | None:
    """'/works/OL29227890W' -> 'OL29227890W'."""
    return key.rsplit("/", 1)[-1] if key else None


def _year(publish_date: str | None) -> int | None:
    # Open Library dates are free text: "2023", "March 7, 2023", "c1998".
    found = re.search(r"(?<!\d)(1[4-9]\d\d|2[01]\d\d)(?!\d)", publish_date or "")
    return int(found.group(1)) if found else None


def _text(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


async def _get(client: httpx2.AsyncClient, path: str) -> dict[str, Any]:
    try:
        response = await client.get(BASE + path)
    except httpx2.HTTPError as exc:
        raise Unavailable(f"Open Library could not be reached: {exc!r}") from exc
    if response.status_code == 404:
        raise NotFound(path)
    if response.status_code >= 400:
        raise Unavailable(f"Open Library answered {response.status_code} for {path}")
    return response.json()


async def find_by_isbn(
    isbn13: str, transport: httpx2.AsyncBaseTransport | None = None
) -> FoundBook:
    """The edition with this ISBN, its work, and the work's authors in order."""
    async with httpx2.AsyncClient(
        transport=transport,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
    ) as client:
        edition = await _get(client, f"/isbn/{isbn13}.json")
        work_id = _key_id((edition.get("works") or [{}])[0].get("key"))
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
                authors.append(FoundAuthor(author_id, name))

    title = _text(work.get("title")) or _text(edition.get("title"))
    if not title:
        raise NotFound(f"/isbn/{isbn13}.json has no title")
    publishers = edition.get("publishers") or []
    covers = [c for c in (edition.get("covers") or work.get("covers") or []) if c and c > 0]
    return FoundBook(
        isbn13=isbn13,
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
