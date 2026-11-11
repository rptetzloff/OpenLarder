"""USDA FoodData Central's generic foods, to link ingredients to
(models/foods.py, migration 0055).

    python -m openlarder.fdc load            # downloads the datasets set
    python -m openlarder.fdc load a.zip ...  # or reads zips already here

Loaded from FDC's bulk download, not its API (SCOPING.md: no key, and no
hourly limit): the CSV zips of Foundation Foods, SR Legacy and the survey
foods, set in OPENLARDER_FDC_DATASETS. Branded products and Foundation's
lab samples are left out. Loading again updates each food in place and
keeps any FDC no longer lists, so no link is lost to a new release.
"""

import argparse
import asyncio
import csv
import io
import sys
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

import httpx2
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from openlarder.models import FdcFood
from openlarder.models.foods import DATA_TYPES
from openlarder.openlibrary import USER_AGENT

TIMEOUT = 120.0
BATCH = 2000


class Unavailable(RuntimeError):
    pass


class BadDataset(ValueError):
    pass


def food_url(fdc_id: int) -> str:
    return f"https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients"


@dataclass
class Food:
    fdc_id: int
    data_type: str
    description: str
    category: str | None
    ndb_number: int | None
    published: date | None


def _csv(archive: zipfile.ZipFile, name: str) -> list[dict[str, str]] | None:
    """A CSV in the zip by its file name, whatever folder it's in."""
    for member in archive.namelist():
        if member.rsplit("/", 1)[-1] == name:
            with archive.open(member) as f:
                return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))
    return None


def _int(raw: str | None) -> int | None:
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def _date(raw: str | None) -> date | None:
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def read(data: bytes) -> list[Food]:
    """The generic foods in one of FDC's CSV zips."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise BadDataset("That isn't a zip file.") from exc
    with archive:
        foods = _csv(archive, "food.csv")
        if foods is None:
            raise BadDataset("No food.csv in it: not one of FoodData Central's CSV downloads.")
        categories = {
            r["id"]: r["description"] for r in _csv(archive, "food_category.csv") or []
        } | {
            r["wweia_food_category"]: r["wweia_food_category_description"]
            for r in _csv(archive, "wweia_food_category.csv") or []
        }
        ndb = {r["fdc_id"]: r["NDB_number"] for r in _csv(archive, "sr_legacy_food.csv") or []}
    out = []
    for row in foods:
        fdc_id = _int(row.get("fdc_id"))
        description = " ".join((row.get("description") or "").split())
        if row.get("data_type") not in DATA_TYPES or fdc_id is None or not description:
            continue
        out.append(
            Food(
                fdc_id=fdc_id,
                data_type=row["data_type"],
                description=description,
                category=categories.get(row.get("food_category_id") or ""),
                ndb_number=_int(ndb.get(row["fdc_id"])),
                published=_date(row.get("publication_date")),
            )
        )
    return out


async def download(urls: Iterable[str], transport: httpx2.AsyncBaseTransport | None = None):
    """Each dataset's zip, in turn."""
    async with httpx2.AsyncClient(
        transport=transport,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
        follow_redirects=True,
    ) as client:
        for url in urls:
            try:
                response = await client.get(url)
            except httpx2.HTTPError as exc:
                raise Unavailable(f"FoodData Central could not be reached: {exc!r}") from exc
            if response.status_code >= 400:
                raise Unavailable(
                    f"FoodData Central answered {response.status_code} for {url.rsplit('/', 1)[-1]}"
                )
            yield response.content


async def save(session: AsyncSession, foods: list[Food]) -> int:
    """Add or update each food; how many. The caller commits."""
    foods = list({f.fdc_id: f for f in foods}.values())
    for i in range(0, len(foods), BATCH):
        rows = [f.__dict__ for f in foods[i : i + BATCH]]
        statement = insert(FdcFood).values(rows)
        await session.execute(
            statement.on_conflict_do_update(
                index_elements=[FdcFood.fdc_id],
                set_={
                    "data_type": statement.excluded.data_type,
                    "description": statement.excluded.description,
                    "category": statement.excluded.category,
                    "ndb_number": statement.excluded.ndb_number,
                    "published": statement.excluded.published,
                    "loaded_at": func.now(),
                },
            )
        )
    return len(foods)


async def load(
    session: AsyncSession, urls: Iterable[str], transport: httpx2.AsyncBaseTransport | None = None
) -> int:
    """Download every dataset and save its foods; how many. Nothing is
    saved unless all are read. The caller commits."""
    foods: list[Food] = []
    async for data in download(urls, transport):
        foods += read(data)
    return await save(session, foods)


@dataclass
class Status:
    foods: int
    loaded_at: datetime | None


async def status(session: AsyncSession) -> Status:
    count, newest = (await session.execute(select(func.count(), func.max(FdcFood.loaded_at)))).one()
    return Status(foods=count, loaded_at=newest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m openlarder.fdc", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    loading = commands.add_parser("load", help="load FoodData Central's generic foods")
    loading.add_argument("zips", nargs="*", help="dataset zips already downloaded")
    args = parser.parse_args(argv)

    from openlarder.config import get_settings
    from openlarder.db import dispose_engine, session_factory

    async def run() -> int:
        try:
            async with session_factory()() as session:
                if args.zips:
                    foods: list[Food] = []
                    for path in args.zips:
                        with open(path, "rb") as f:
                            foods += read(f.read())
                    n = await save(session, foods)
                else:
                    n = await load(session, get_settings().fdc_datasets)
                await session.commit()
            print(f"{n:,} foods from FoodData Central.")
            return 0
        finally:
            await dispose_engine()

    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
