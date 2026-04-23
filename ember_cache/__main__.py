"""Entrypoint: ``python -m ember_cache``."""

from __future__ import annotations

import asyncio
import contextlib
import os

from .logging_setup import configure
from .server import serve


def main() -> None:
    configure()
    host = os.getenv("HOST", "0.0.0.0")  # noqa: S104 - intended bind for container use
    port = int(os.getenv("PORT", "9888"))
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve(host, port))


if __name__ == "__main__":
    main()
