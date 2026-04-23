"""Basic single-client command coverage."""

from __future__ import annotations

from conftest import Client


async def test_put_then_get(client: Client) -> None:
    assert await client.send("PUT key1 hello") == {"status": "Ok"}
    assert await client.send("GET key1") == {"status": "Ok", "result": "hello"}


async def test_get_unknown_returns_null(client: Client) -> None:
    assert await client.send("GET missing") == {"status": "Ok", "result": None}


async def test_del_removes_key(client: Client) -> None:
    await client.send("PUT k v")
    assert await client.send("DEL k") == {"status": "Ok"}
    assert await client.send("GET k") == {"status": "Ok", "result": None}


async def test_del_unknown_is_ok(client: Client) -> None:
    # Deleting a non-existent key is a no-op (idempotent), per documented assumption.
    assert await client.send("DEL nope") == {"status": "Ok"}


async def test_put_value_with_spaces_and_json(client: Client) -> None:
    payload = '{"first_name": "George", "last_name": "Washington"}'
    assert await client.send(f"PUT georgew {payload}") == {"status": "Ok"}
    assert await client.send("GET georgew") == {"status": "Ok", "result": payload}


async def test_put_overwrites(client: Client) -> None:
    await client.send("PUT k a")
    await client.send("PUT k b")
    assert await client.send("GET k") == {"status": "Ok", "result": "b"}


async def test_unknown_command(client: Client) -> None:
    resp = await client.send("FOO bar")
    assert resp["status"] == "Error"
    assert resp["error_code"] == "INVALID_COMMAND"


async def test_put_missing_value(client: Client) -> None:
    resp = await client.send("PUT only_key")
    assert resp["status"] == "Error"
    assert resp["error_code"] == "INVALID_ARGS"


async def test_get_missing_key_arg(client: Client) -> None:
    resp = await client.send("GET")
    assert resp["status"] == "Error"
    assert resp["error_code"] == "INVALID_ARGS"


async def test_case_insensitive_verb(client: Client) -> None:
    assert await client.send("put k v") == {"status": "Ok"}
    assert await client.send("get k") == {"status": "Ok", "result": "v"}


async def test_ping(client: Client) -> None:
    assert await client.send("PING") == {"status": "Ok", "result": "PONG"}
