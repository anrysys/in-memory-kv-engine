"""Command dispatcher: maps parsed verbs to engine operations."""

from __future__ import annotations

from .errors import INVALID_COMMAND, CommandError
from .protocol import err, ok, ok_with_result, parse_command
from .store import KVStore
from .transaction import Session


async def handle_line(session: Session, store: KVStore, line: str) -> str:
    """Parse a single command line and execute it; return the response line.

    All :class:`CommandError` instances are converted into Error JSON. Any
    unexpected exception bubbles up to the server layer, which logs it and
    returns a generic INTERNAL error so the connection survives.
    """
    try:
        verb, args = parse_command(line)
    except CommandError as exc:
        return err(exc.code, exc.message)

    try:
        if verb == "PUT":
            await session.put(store, args[0], args[1])
            return ok()
        if verb == "GET":
            value = session.get(store, args[0])
            return ok_with_result(value)
        if verb == "DEL":
            await session.delete(store, args[0])
            return ok()
        if verb == "START":
            session.begin()
            return ok()
        if verb == "COMMIT":
            await session.commit(store)
            return ok()
        if verb == "ROLLBACK":
            session.rollback()
            return ok()
        if verb == "PING":
            return ok_with_result("PONG")
    except CommandError as exc:
        return err(exc.code, exc.message)

    # Should be unreachable because parse_command validates the verb.
    return err(INVALID_COMMAND, f"Unhandled command: {verb}")
