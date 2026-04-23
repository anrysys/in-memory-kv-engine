"""Atomic in-memory key/value store.

The store is the single source of truth for committed data. All mutations are
funneled through :meth:`KVStore.apply`, which holds an ``asyncio.Lock`` so that
each transaction's writeset becomes visible to other clients atomically (the
"all-or-nothing" guarantee required by the assignment).

Reads (:meth:`get`) are lock-free. Under a single-threaded asyncio event loop
this is safe: dict reads are not interleaved with the critical section in
:meth:`apply` because we never ``await`` between the lock acquisition and the
mutation.
"""

from __future__ import annotations

import asyncio
from typing import Literal

# A writeset entry is either ("set", value) or ("del",).
WriteOp = tuple[Literal["set"], str] | tuple[Literal["del"]]
WriteSet = dict[str, WriteOp]


class KVStore:
    """In-memory key/value store with an atomic writeset apply primitive."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._lock = asyncio.Lock()

    def get(self, key: str) -> str | None:
        """Return the committed value for ``key`` or ``None`` if absent."""
        return self._data.get(key)

    async def apply(self, writeset: WriteSet) -> None:
        """Atomically apply a transaction's writeset to the committed store."""
        if not writeset:
            return
        async with self._lock:
            for key, op in writeset.items():
                if op[0] == "set":
                    self._data[key] = op[1]
                else:  # "del"
                    self._data.pop(key, None)

    def snapshot(self) -> dict[str, str]:
        """Return a shallow copy of the committed store (test/debug helper)."""
        return dict(self._data)
