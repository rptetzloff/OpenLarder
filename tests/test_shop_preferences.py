"""Each person's buy-link shops: their order, and those hidden (one stays)."""

from fake_broker import _sign_in

ALL = ["bookshop", "bn", "thriftbooks", "bookoutlet", "amazon", "kobo"]


async def test_none_until_chosen_then_kept(client, broker) -> None:
    await _sign_in(client, broker)
    assert (await client.get("/api/auth/me")).json()["shops"] is None
    saved = await client.put(
        "/api/account/shops",
        json={"order": ["thriftbooks", "bookshop", "thriftbooks"], "hidden": ["amazon"]},
    )
    assert saved.status_code == 200, saved.text
    # Each once, in the order given.
    assert saved.json()["shops"] == {"order": ["thriftbooks", "bookshop"], "hidden": ["amazon"]}
    assert (await client.get("/api/auth/me")).json()["shops"] == saved.json()["shops"]


async def test_one_shop_must_be_left_showing(client, broker) -> None:
    await _sign_in(client, broker)
    refused = await client.put("/api/account/shops", json={"hidden": ALL})
    assert refused.status_code == 422
    assert "at least one" in refused.json()["detail"]
    kept = await client.put("/api/account/shops", json={"hidden": ALL[1:]})
    assert kept.status_code == 200


async def test_an_unknown_shop_is_refused(client, broker) -> None:
    await _sign_in(client, broker)
    for body in ({"order": ["waterstones"]}, {"hidden": ["audible"]}):
        assert (await client.put("/api/account/shops", json=body)).status_code == 422


async def test_signed_out_it_isnt_kept_here(client) -> None:
    assert (await client.put("/api/account/shops", json={"hidden": ["amazon"]})).status_code == 401
