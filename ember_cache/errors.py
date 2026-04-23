"""Error code constants and the protocol-level exception type."""

from __future__ import annotations

INVALID_COMMAND = "INVALID_COMMAND"
INVALID_ARGS = "INVALID_ARGS"
NO_TRANSACTION = "NO_TRANSACTION"
NESTED_TRANSACTION = "NESTED_TRANSACTION"
UNKNOWN_KEY = "UNKNOWN_KEY"
INTERNAL = "INTERNAL"


class CommandError(Exception):
    """Raised when a client command cannot be executed; carries a stable error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
