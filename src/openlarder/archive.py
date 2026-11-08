"""The Internet Archive: a copy of a web recipe's page, from when it was added.

A website's page can disappear; the Wayback Machine keeps copies. When a
web recipe is added, OpenLarder asks the Archive's Save Page Now service to
capture its page, and keeps the snapshot's address. If that fails, it asks
the availability service for the copy nearest to when the page was added,
which may be one somebody else saved. *Ray, 2026-11-08: "say that it's
archived and try to link to internet archive from when it was added".*

Save Page Now works without an account, with lower limits; with an
archive.org account's API keys (OPENLARDER_ARCHIVE_ACCESS_KEY and
OPENLARDER_ARCHIVE_SECRET_KEY) it uses those. The API is documented in a
public document kept by the Archive's developers, not on archive.org
itself; checked 2026-11-08: POST /save with the address returns a job, and
GET /save/status/<job> says when it's done. A "too many requests" answer
means wait; the page is tried again later, never in a loop here.

Only the page's address is sent: OpenLarder never fetches the page itself.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx2

SAVE = "https://web.archive.org/save"
AVAILABLE = "https://archive.org/wayback/available"
WEB = "https://web.archive.org/web"
USER_AGENT = "OpenLarder/0.1 (https://openlarder.com; privacy@openlarder.com)"
TIMEOUT = 30.0
# How often and how long to wait for a capture: about two minutes. Tests set
# POLL_EVERY to 0.
POLL_EVERY = 5.0
POLLS = 24


@dataclass
class Snapshot:
    url: str
    at: datetime


def _when(timestamp: str) -> datetime:
    """A Wayback timestamp, "20261108153000", as a time."""
    return datetime.strptime(timestamp[:14].ljust(14, "0"), "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def _client(transport: httpx2.AsyncBaseTransport | None) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        transport=transport, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
    )


async def save(
    client: httpx2.AsyncClient, url: str, keys: tuple[str, str] | None
) -> Snapshot | None:
    """Ask Save Page Now to capture the page, and wait for the copy. None if
    it refuses, fails, or takes too long."""
    headers = {"Accept": "application/json"}
    if keys:
        headers["Authorization"] = f"LOW {keys[0]}:{keys[1]}"
    try:
        response = await client.post(SAVE, data={"url": url}, headers=headers)
        if response.status_code != 200:
            return None
        job = response.json().get("job_id")
        if not job:
            return None
        for _ in range(POLLS):
            await asyncio.sleep(POLL_EVERY)
            status = await client.get(f"{SAVE}/status/{job}", headers=headers)
            if status.status_code != 200:
                return None
            body = status.json()
            if body.get("status") == "success" and body.get("timestamp"):
                original = body.get("original_url") or url
                return Snapshot(f"{WEB}/{body['timestamp']}/{original}", _when(body["timestamp"]))
            if body.get("status") != "pending":
                return None
    except (httpx2.HTTPError, ValueError):
        return None
    return None


async def nearest(client: httpx2.AsyncClient, url: str, when: datetime) -> Snapshot | None:
    """The Archive's copy of the page nearest to a time, if it has one."""
    try:
        response = await client.get(
            AVAILABLE, params={"url": url, "timestamp": when.strftime("%Y%m%d%H%M%S")}
        )
        if response.status_code != 200:
            return None
        closest = (response.json().get("archived_snapshots") or {}).get("closest") or {}
    except (httpx2.HTTPError, ValueError):
        return None
    if not closest.get("available") or not closest.get("url") or not closest.get("timestamp"):
        return None
    return Snapshot(closest["url"].replace("http://", "https://", 1), _when(closest["timestamp"]))


async def copy_of(
    url: str,
    added: datetime,
    keys: tuple[str, str] | None = None,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> Snapshot | None:
    """A copy of the page: a capture made now, or else the nearest to when
    it was added."""
    async with _client(transport) as client:
        return await save(client, url, keys) or await nearest(client, url, added)
