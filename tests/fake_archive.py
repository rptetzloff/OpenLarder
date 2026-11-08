"""A fake Internet Archive: Save Page Now and the availability service.

Every test gets one (conftest), so nothing ever reaches the real Archive.
By default it refuses everything, as an Archive that's down would; tests
set what it answers.
"""

import httpx2


class FakeArchive:
    def __init__(self) -> None:
        # Save Page Now: None refuses; else the answers a job's status gives
        # in turn, the last repeated.
        self.statuses: list[dict] | None = None
        self.save_code = 200
        # The availability service's closest copy, or None for none.
        self.closest: dict | None = None
        self.requests: list[httpx2.Request] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        path = request.url.path
        if request.url.host == "web.archive.org" and path == "/save" and request.method == "POST":
            if self.statuses is None:
                return httpx2.Response(503)
            return httpx2.Response(self.save_code, json={"url": "x", "job_id": "job-1"})
        if request.url.host == "web.archive.org" and path == "/save/status/job-1":
            assert self.statuses is not None
            answer = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return httpx2.Response(200, json=answer)
        if request.url.host == "archive.org" and path == "/wayback/available":
            snapshots = {"closest": self.closest} if self.closest else {}
            return httpx2.Response(
                200, json={"url": request.url.params["url"], "archived_snapshots": snapshots}
            )
        return httpx2.Response(404)
