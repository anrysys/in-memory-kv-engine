"""Asyncio TCP server for Ember Cache."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from .commands import handle_line
from .errors import INTERNAL
from .protocol import err
from .store import KVStore
from .transaction import Session

log = logging.getLogger("ember_cache.server")


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    store: KVStore,
) -> None:
    peer = writer.get_extra_info("peername")
    peer_label = f"{peer[0]}:{peer[1]}" if peer else "?"
    session = Session()
    log.info("client connected %s", peer_label)

    try:
        while not reader.at_eof():
            try:
                raw = await reader.readline()
            except (ConnectionResetError, asyncio.IncompleteReadError):
                break
            if not raw:
                break

            try:
                line = raw.decode("utf-8")
            except UnicodeDecodeError:
                writer.write(err(INTERNAL, "Invalid UTF-8 input").encode("utf-8"))
                await writer.drain()
                continue

            if not line.strip():
                # Skip empty/whitespace-only lines silently.
                continue

            try:
                response = await handle_line(session, store, line)
            except Exception:  # noqa: BLE001 - last-resort safety net
                log.exception("unhandled error from %s while processing %r", peer_label, line)
                response = err(INTERNAL, "Unexpected server error")

            writer.write(response.encode("utf-8"))
            try:
                await writer.drain()
            except ConnectionResetError:
                break
    finally:
        log.info("client disconnected %s", peer_label)
        with contextlib.suppress(Exception):  # noqa: BLE001 - cleanup best-effort
            writer.close()
            await writer.wait_closed()


async def serve(host: str, port: int, store: KVStore | None = None) -> None:
    """Run the server until cancelled."""
    store = store or KVStore()

    server = await asyncio.start_server(
        lambda r, w: _handle_client(r, w, store),
        host=host,
        port=port,
    )
    sockets = server.sockets or ()
    bound = ", ".join(str(s.getsockname()) for s in sockets)
    log.info("ember-cache listening on %s", bound)

    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    def _request_stop(sig: signal.Signals) -> None:
        log.info("received signal %s, shutting down", sig.name)
        if not stop.done():
            stop.set_result(None)

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # pragma: no cover - Windows
            loop.add_signal_handler(sig, _request_stop, sig)

    async with server:
        serve_task = asyncio.create_task(server.serve_forever())
        await stop
        serve_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):  # noqa: BLE001
            await serve_task

    log.info("ember-cache stopped")
