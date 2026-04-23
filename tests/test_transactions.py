"""Transaction semantics: START / COMMIT / ROLLBACK and error cases."""

from __future__ import annotations

from conftest import Client


async def test_transaction_commit_visible(kv_server, client: Client) -> None:
    host, port = kv_server
    await client.send("START")
    await client.send("PUT k inside_tx")
    # Inside the transaction, reads see the buffered write.
    assert await client.send("GET k") == {"status": "Ok", "result": "inside_tx"}
    # A second connection does not see uncommitted writes.
    other = await Client.connect(host, port)
    try:
        assert await other.send("GET k") == {"status": "Ok", "result": None}
    finally:
        await other.close()
    # After COMMIT both clients agree.
    assert await client.send("COMMIT") == {"status": "Ok"}
    other = await Client.connect(host, port)
    try:
        assert await other.send("GET k") == {"status": "Ok", "result": "inside_tx"}
    finally:
        await other.close()


async def test_transaction_rollback_discards(client: Client) -> None:
    await client.send("PUT k initial")
    await client.send("START")
    await client.send("PUT k changed")
    await client.send("DEL other")
    assert await client.send("GET k") == {"status": "Ok", "result": "changed"}
    assert await client.send("ROLLBACK") == {"status": "Ok"}
    assert await client.send("GET k") == {"status": "Ok", "result": "initial"}


async def test_nested_start_is_error(client: Client) -> None:
    await client.send("START")
    resp = await client.send("START")
    assert resp["status"] == "Error"
    assert resp["error_code"] == "NESTED_TRANSACTION"
    await client.send("ROLLBACK")


async def test_commit_without_transaction(client: Client) -> None:
    resp = await client.send("COMMIT")
    assert resp["status"] == "Error"
    assert resp["error_code"] == "NO_TRANSACTION"


async def test_rollback_without_transaction(client: Client) -> None:
    resp = await client.send("ROLLBACK")
    assert resp["status"] == "Error"
    assert resp["error_code"] == "NO_TRANSACTION"


async def test_tx_delete_then_get_returns_null(client: Client) -> None:
    await client.send("PUT k v")
    await client.send("START")
    await client.send("DEL k")
    assert await client.send("GET k") == {"status": "Ok", "result": None}
    await client.send("COMMIT")
    assert await client.send("GET k") == {"status": "Ok", "result": None}


async def test_spec_example_sequence(kv_server, client: Client) -> None:
    """Reproduce the example sequence from the assignment verbatim."""
    host, port = kv_server
    assert await client.send("PUT most_popular_leader georgew") == {"status": "Ok"}
    assert await client.send("START") == {"status": "Ok"}
    assert await client.send("GET most_popular_leader") == {
        "status": "Ok",
        "result": "georgew",
    }
    george = '{"first_name": "George", "last_name": "Washington", "role": "President"}'
    winston = '{"first_name": "Winston", "last_name": "Churchill", "role": "Prime Minister"}'
    assert await client.send(f"PUT georgew {george}") == {"status": "Ok"}
    assert await client.send(f"PUT winstonc {winston}") == {"status": "Ok"}
    assert await client.send("COMMIT") == {"status": "Ok"}

    # A fresh client sees the committed values.
    other = await Client.connect(host, port)
    try:
        assert await other.send("GET georgew") == {"status": "Ok", "result": george}
        assert await other.send("GET winstonc") == {"status": "Ok", "result": winston}
    finally:
        await other.close()
