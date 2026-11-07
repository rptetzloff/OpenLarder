"""Display names: chosen in OpenLarder, unique ignoring case, never overwritten
by signing in. The rules themselves are tested on names.validate, without a
request; the rest goes through the routes and the database."""

import pytest
from alembic import command
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from fake_broker import ISSUER, _settings, _sign_in
from openlarder import names

PUT = "/api/account/display-name"


@pytest.mark.parametrize(
    "raw, stored",
    [
        ("Sarah", "Sarah"),
        ("  Sarah   Jane  ", "Sarah Jane"),
        ("Ｓａｒａｈ", "Sarah"),  # full-width letters fold to the same name
        ("O'Brien-Smith", "O'Brien-Smith"),
        ("jane.doe_2", "jane.doe_2"),
        ("Zoë", "Zoë"),
        ("渡辺", "渡辺"),
    ],
)
def test_valid_names_are_normalised(raw, stored) -> None:
    assert names.validate(raw) == stored


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "S",
        "x" * 33,
        "-Sarah",
        "Sarah-",
        "Sa--rah",
        "Sarah!",
        "<script>",
        "Admin",
        "OPENLARDER",
        "moderator",
    ],
)
def test_invalid_names_are_refused(raw) -> None:
    with pytest.raises(names.InvalidName):
        names.validate(raw)


async def test_a_first_sign_in_asks_for_a_name(client, broker) -> None:
    await _sign_in(client, broker)
    me = (await client.get("/api/auth/me")).json()
    assert me["display_name"] is None
    assert me["suggested_name"] == "Test Cook"


async def test_a_provider_name_that_fails_the_rules_suggests_nothing(client, broker) -> None:
    broker.name = "admin"
    await _sign_in(client, broker)
    assert (await client.get("/api/auth/me")).json()["suggested_name"] is None


async def test_choosing_a_name_stores_it_and_drops_the_suggestion(client, broker, adb) -> None:
    await _sign_in(client, broker)
    response = await client.put(PUT, json={"display_name": "  Sarah  "})

    assert response.status_code == 200
    assert response.json()["display_name"] == "Sarah"
    assert response.json()["suggested_name"] is None
    row = (await adb.execute(text("SELECT display_name, suggested_name FROM users"))).one()
    assert tuple(row) == ("Sarah", None)


async def test_signing_in_again_never_overwrites_a_chosen_name(client, broker, adb) -> None:
    await _sign_in(client, broker)
    await client.put(PUT, json={"display_name": "Sarah"})
    broker.name = "Provider Name"
    await _sign_in(client, broker)

    me = (await client.get("/api/auth/me")).json()
    assert me["display_name"] == "Sarah"
    assert me["suggested_name"] is None
    assert await adb.scalar(text("SELECT suggested_name FROM users")) is None


async def test_a_name_is_taken_whatever_its_case(client, broker) -> None:
    await _sign_in(client, broker)
    assert (await client.put(PUT, json={"display_name": "Sarah"})).status_code == 200

    broker.subject = "someone-else"
    await _sign_in(client, broker)
    response = await client.put(PUT, json={"display_name": "SARAH"})
    assert response.status_code == 409
    assert (await client.get("/api/auth/me")).json()["display_name"] is None


async def test_keeping_your_own_name_in_another_case_is_allowed(client, broker) -> None:
    await _sign_in(client, broker)
    await client.put(PUT, json={"display_name": "sarah"})
    response = await client.put(PUT, json={"display_name": "Sarah"})
    assert (response.status_code, response.json()["display_name"]) == (200, "Sarah")


async def test_an_invalid_name_says_why(client, broker) -> None:
    await _sign_in(client, broker)
    response = await client.put(PUT, json={"display_name": "Admin"})
    assert response.status_code == 422
    assert response.json()["detail"] == "That name is reserved."


async def test_choosing_a_name_needs_a_session(client) -> None:
    assert (await client.put(PUT, json={"display_name": "Sarah"})).status_code == 401


async def test_another_sites_page_cannot_change_a_name(client, broker) -> None:
    await _sign_in(client, broker)
    response = await client.put(
        PUT, json={"display_name": "Mallory"}, headers={"Origin": "https://auth.openlarder.com"}
    )
    assert response.status_code == 403
    assert (await client.get("/api/auth/me")).json()["display_name"] is None


async def test_the_sites_own_page_can(client, broker, configure) -> None:
    await _sign_in(client, broker)
    response = await client.put(
        PUT, json={"display_name": "Sarah"}, headers={"Origin": "http://testserver"}
    )
    assert response.status_code == 200


async def test_me_points_at_the_brokers_account_page(client, broker, configure) -> None:
    configure(_settings(oidc_issuer="https://auth.example.test"))
    assert (await client.get("/api/auth/me")).status_code == 401  # nobody signed in yet
    configure(_settings())
    await _sign_in(client, broker)
    assert (await client.get("/api/auth/me")).json()["account_url"] == (
        ISSUER.rstrip("/") + "/settings"
    )


def _refused(db: Connection, sql: str, **params) -> None:
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(text(sql), params)


def test_the_database_holds_names_unique_and_trimmed(db: Connection) -> None:
    insert = "INSERT INTO users (issuer, subject, display_name) VALUES ('i', :s, :n)"
    db.execute(text(insert), {"s": "a", "n": "Sarah"})
    _refused(db, insert, s="b", n="sARAH")
    _refused(db, insert, s="c", n=" Padded")
    _refused(db, insert, s="d", n="S")
    _refused(db, insert, s="e", n="x" * 33)
    _refused(db, "INSERT INTO users (issuer, subject, suggested_name) VALUES ('i', 'f', '')")
    # Unchosen names are empty, and any number of people can have none.
    db.execute(text("INSERT INTO users (issuer, subject) VALUES ('i', 'g'), ('i', 'h')"))


def test_migration_moves_existing_names_to_suggestions(engine, alembic_config) -> None:
    engine.dispose()
    command.downgrade(alembic_config, "0007")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (issuer, subject, display_name) VALUES"
                    " ('m', 'named', 'Old Name'), ('m', 'fallback', 'OpenLarder user')"
                )
            )
        command.upgrade(alembic_config, "head")
        with engine.connect() as conn:
            rows = dict(
                conn.execute(
                    text(
                        "SELECT subject, suggested_name FROM users WHERE issuer = 'm'"
                        " AND display_name IS NULL"
                    )
                ).all()
            )
        assert rows == {"named": "Old Name", "fallback": None}
    finally:
        command.upgrade(alembic_config, "head")
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE issuer = 'm'"))
