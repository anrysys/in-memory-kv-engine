"""Shared pytest fixtures: spin up a real server and provide a send helper."""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from collections.abc import AsyncIterator, Iterable

import pytest

from ember_cache.server import serve
from ember_cache.store import KVStore


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def kv_server() -> AsyncIterator[tuple[str, int]]:
    """Start an in-process Ember Cache server on a random port."""
    host, port = "127.0.0.1", _free_port()
    store = KVStore()
    task = asyncio.create_task(serve(host, port, store))
    # Wait until the port accepts connections.
    for _ in range(50):
        try:
            _, w = await asyncio.open_connection(host, port)
            w.close()
            await w.wait_closed()
            break
        except OSError:
            await asyncio.sleep(0.02)
    else:  # pragma: no cover
        task.cancel()
        raise RuntimeError("server did not start in time")

    try:
        yield host, port
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):  # noqa: BLE001
            await task


class Client:
    """Tiny async client used by tests."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer

    @classmethod
    async def connect(cls, host: str, port: int) -> Client:
        reader, writer = await asyncio.open_connection(host, port)
        return cls(reader, writer)

    async def send(self, command: str) -> dict:
        self.writer.write((command + "\n").encode("utf-8"))
        await self.writer.drain()
        line = await self.reader.readline()
        assert line, "server closed connection unexpectedly"
        return json.loads(line.decode("utf-8"))

    async def send_many(self, commands: Iterable[str]) -> list[dict]:
        return [await self.send(cmd) for cmd in commands]

    async def close(self) -> None:
        self.writer.close()
        with contextlib.suppress(ConnectionResetError, BrokenPipeError):
            await self.writer.wait_closed()


@pytest.fixture
async def client(kv_server: tuple[str, int]) -> AsyncIterator[Client]:
    host, port = kv_server
    c = await Client.connect(host, port)
    try:
        yield c
    finally:
        await c.close()
