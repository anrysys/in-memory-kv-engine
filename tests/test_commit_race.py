"""Concurrency: COMMIT atomicity under racing transactions."""

from __future__ import annotations

import asyncio

from conftest import Client


async def _run_tx(host: str, port: int, key: str, value: str) -> None:
    c = await Client.connect(host, port)
    try:
        await c.send("START")
        await c.send(f"PUT {key} {value}")
        # Yield to the event loop to interleave with peer transactions.
        await asyncio.sleep(0)
        await c.send(f"PUT {key}_marker yes")
        await c.send("COMMIT")
    finally:
        await c.close()


async def test_concurrent_disjoint_commits_all_apply(kv_server) -> None:
    """N concurrent transactions on disjoint keys must all be visible after COMMIT."""
    host, port = kv_server
    n = 25
    await asyncio.gather(*[_run_tx(host, port, f"key{i}", f"value{i}") for i in range(n)])

    verifier = await Client.connect(host, port)
    try:
        for i in range(n):
            assert await verifier.send(f"GET key{i}") == {
                "status": "Ok",
                "result": f"value{i}",
            }
            assert await verifier.send(f"GET key{i}_marker") == {
                "status": "Ok",
                "result": "yes",
            }
    finally:
        await verifier.close()


async def test_concurrent_same_key_last_write_wins(kv_server) -> None:
    """Two concurrent transactions on the same key: result is one of the values, never partial."""
    host, port = kv_server

    async def writer(value: str) -> None:
        c = await Client.connect(host, port)
        try:
            await c.send("START")
            await c.send(f"PUT shared {value}")
            await asyncio.sleep(0)
            await c.send("COMMIT")
        finally:
            await c.close()

    await asyncio.gather(writer("alpha"), writer("beta"))

    verifier = await Client.connect(host, port)
    try:
        resp = await verifier.send("GET shared")
        assert resp["status"] == "Ok"
        assert resp["result"] in {"alpha", "beta"}
    finally:
        await verifier.close()


async def test_writeset_applied_atomically(kv_server) -> None:
    """An observer must never see a partial commit (only some keys of a tx)."""
    host, port = kv_server
    barrier = asyncio.Event()

    async def writer() -> None:
        c = await Client.connect(host, port)
        try:
            await c.send("START")
            for i in range(50):
                await c.send(f"PUT atom{i} v")
            barrier.set()
            await c.send("COMMIT")
        finally:
            await c.close()

    async def observer() -> None:
        c = await Client.connect(host, port)
        try:
            await barrier.wait()
            # Spin a few times trying to catch a partial state. The point is
            # that whenever atom0 is visible, atom49 must also be visible.
            for _ in range(100):
                first = await c.send("GET atom0")
                last = await c.send("GET atom49")
                assert (first["result"] is None) == (
                    last["result"] is None
                ), "observed partial commit"
                await asyncio.sleep(0)
        finally:
            await c.close()

    await asyncio.gather(writer(), observer())
