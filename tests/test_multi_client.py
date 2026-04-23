"""Multi-client isolation and read-committed visibility."""

from __future__ import annotations

from conftest import Client


async def test_read_committed_visibility(kv_server) -> None:
    """Within a transaction, reads see data committed by other clients."""
    host, port = kv_server
    a = await Client.connect(host, port)
    b = await Client.connect(host, port)
    try:
        await a.send("START")
        await a.send("PUT a_key from_a")
        # B commits an unrelated key while A's transaction is open.
        assert await b.send("PUT b_key from_b") == {"status": "Ok"}
        # A sees its own buffered write...
        assert await a.send("GET a_key") == {"status": "Ok", "result": "from_a"}
        # ...and the freshly committed value from B (read-committed).
        assert await a.send("GET b_key") == {"status": "Ok", "result": "from_b"}
        await a.send("COMMIT")
        # B sees A's committed write.
        assert await b.send("GET a_key") == {"status": "Ok", "result": "from_a"}
    finally:
        await a.close()
        await b.close()


async def test_uncommitted_writes_invisible_to_others(kv_server) -> None:
    host, port = kv_server
    a = await Client.connect(host, port)
    b = await Client.connect(host, port)
    try:
        await a.send("START")
        await a.send("PUT secret hidden")
        assert await b.send("GET secret") == {"status": "Ok", "result": None}
        await a.send("ROLLBACK")
        assert await b.send("GET secret") == {"status": "Ok", "result": None}
    finally:
        await a.close()
        await b.close()


async def test_each_session_has_independent_transaction(kv_server) -> None:
    host, port = kv_server
    a = await Client.connect(host, port)
    b = await Client.connect(host, port)
    try:
        await a.send("START")
        # B can start its own transaction independently.
        assert await b.send("START") == {"status": "Ok"}
        await a.send("PUT k from_a")
        await b.send("PUT k from_b")
        # Each sees only its own buffered write.
        assert await a.send("GET k") == {"status": "Ok", "result": "from_a"}
        assert await b.send("GET k") == {"status": "Ok", "result": "from_b"}
        await a.send("ROLLBACK")
        await b.send("COMMIT")
        # The committed value is B's.
        assert await a.send("GET k") == {"status": "Ok", "result": "from_b"}
    finally:
        await a.close()
        await b.close()
