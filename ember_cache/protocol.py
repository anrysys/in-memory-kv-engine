"""Wire protocol: command parsing and JSON response building.

Framing
-------
Each command is a single UTF-8 line terminated by ``\\n``. Each response is a
single UTF-8 JSON object terminated by ``\\n``. This is the simplest framing
that satisfies the assignment ("plain socket connection ... UTF-8 strings")
and works with ``nc``/``telnet`` out of the box.

Parsing rules
-------------
* Commands are case-insensitive (``PUT``, ``put`` are equivalent).
* ``PUT`` takes a key and a value; the value is everything after the second
  whitespace block, so values may contain spaces and JSON literals (e.g.
  ``PUT user {"name": "George Washington"}``).
* ``GET`` and ``DEL`` take exactly one argument (the key).
* ``START``, ``COMMIT``, ``ROLLBACK``, ``PING`` take no arguments.
* Empty lines are ignored at the server layer (handled by the dispatcher).

Assumption: keys and values cannot contain a literal ``\\n``. Callers that
need to store newline-bearing payloads should encode them (e.g. JSON-escape).
"""

from __future__ import annotations

import json

from .errors import INVALID_ARGS, INVALID_COMMAND, CommandError

# Verbs that take no arguments.
_NO_ARG_VERBS = frozenset({"START", "COMMIT", "ROLLBACK", "PING"})
# Verbs that take exactly one argument (a key).
_ONE_ARG_VERBS = frozenset({"GET", "DEL"})
# Known verbs (used for the "unknown command" check).
_KNOWN_VERBS = _NO_ARG_VERBS | _ONE_ARG_VERBS | {"PUT"}


def parse_command(line: str) -> tuple[str, list[str]]:
    """Parse a single command line.

    Returns a ``(verb, args)`` tuple. Raises :class:`CommandError` on
    malformed input. The caller is responsible for stripping the trailing
    newline and skipping empty lines.
    """
    stripped = line.strip()
    if not stripped:
        # Defensive: server should skip empty lines before reaching here.
        raise CommandError(INVALID_COMMAND, "Empty command")

    # Use maxsplit=2 so PUT preserves spaces in the value.
    parts = stripped.split(maxsplit=2)
    verb = parts[0].upper()

    if verb not in _KNOWN_VERBS:
        raise CommandError(INVALID_COMMAND, f"Unknown command: {parts[0]!r}")

    if verb in _NO_ARG_VERBS:
        if len(parts) != 1:
            raise CommandError(INVALID_ARGS, f"{verb} takes no arguments")
        return verb, []

    if verb in _ONE_ARG_VERBS:
        if len(parts) != 2:
            raise CommandError(INVALID_ARGS, f"{verb} requires exactly 1 argument: key")
        return verb, [parts[1]]

    # PUT: key + value
    if len(parts) != 3:
        raise CommandError(INVALID_ARGS, "PUT requires 2 arguments: key and value")
    return verb, [parts[1], parts[2]]


def ok(mesg: str | None = None) -> str:
    """Build an Ok JSON response line without a ``result`` field."""
    payload: dict[str, object] = {"status": "Ok"}
    if mesg is not None:
        payload["mesg"] = mesg
    return json.dumps(payload, ensure_ascii=False) + "\n"


def ok_with_result(result: str | None, mesg: str | None = None) -> str:
    """Build an Ok JSON response line that always includes ``result`` (even if None).

    A ``null`` result is the documented signal for "cache miss" on GET.
    """
    payload: dict[str, object] = {"status": "Ok", "result": result}
    if mesg is not None:
        payload["mesg"] = mesg
    return json.dumps(payload, ensure_ascii=False) + "\n"


def err(code: str, mesg: str) -> str:
    """Build an Error JSON response line."""
    payload = {"status": "Error", "error_code": code, "mesg": mesg}
    return json.dumps(payload, ensure_ascii=False) + "\n"
