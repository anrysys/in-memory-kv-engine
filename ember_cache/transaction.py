"""Per-connection session state and transaction semantics.

Isolation model: **read-committed with atomic commit**.

* Outside a transaction, reads and writes go directly to the committed store.
  Single PUT/DEL commands are themselves atomic (single-key writeset).
* Inside a transaction, PUT/DEL are buffered into a per-session writeset.
  GET checks the writeset first, then falls back to the committed store, so
  the transaction sees its own modifications plus any data that was already
  committed (including data committed by other clients while this transaction
  is in flight).
* COMMIT applies the writeset to the store atomically under the store's lock.
* ROLLBACK simply discards the writeset.

This is intentionally simple: there is no write-write conflict detection, so
two transactions modifying the same key produce a "last commit wins" outcome.
See the README for the rationale and trade-offs.
"""

from __future__ import annotations

from .errors import NESTED_TRANSACTION, NO_TRANSACTION, CommandError
from .store import KVStore, WriteSet


class Transaction:
    """Buffered, uncommitted modifications for a single client session."""

    def __init__(self) -> None:
        self.writeset: WriteSet = {}

    def put(self, key: str, value: str) -> None:
        self.writeset[key] = ("set", value)

    def delete(self, key: str) -> None:
        self.writeset[key] = ("del",)

    def get(self, key: str, store: KVStore) -> str | None:
        if key in self.writeset:
            op = self.writeset[key]
            return op[1] if op[0] == "set" else None
        return store.get(key)


class Session:
    """Per-connection state. Holds at most one in-flight transaction."""

    def __init__(self) -> None:
        self.tx: Transaction | None = None

    @property
    def in_transaction(self) -> bool:
        return self.tx is not None

    # ------------------------------------------------------------------ control

    def begin(self) -> None:
        if self.tx is not None:
            raise CommandError(NESTED_TRANSACTION, "A transaction is already in progress")
        self.tx = Transaction()

    async def commit(self, store: KVStore) -> None:
        if self.tx is None:
            raise CommandError(NO_TRANSACTION, "No transaction in progress")
        writeset = self.tx.writeset
        self.tx = None
        await store.apply(writeset)

    def rollback(self) -> None:
        if self.tx is None:
            raise CommandError(NO_TRANSACTION, "No transaction in progress")
        self.tx = None

    # --------------------------------------------------------------------- data

    async def put(self, store: KVStore, key: str, value: str) -> None:
        if self.tx is not None:
            self.tx.put(key, value)
        else:
            await store.apply({key: ("set", value)})

    async def delete(self, store: KVStore, key: str) -> None:
        if self.tx is not None:
            self.tx.delete(key)
        else:
            await store.apply({key: ("del",)})

    def get(self, store: KVStore, key: str) -> str | None:
        if self.tx is not None:
            return self.tx.get(key, store)
        return store.get(key)
