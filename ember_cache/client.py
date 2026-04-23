"""Minimal interactive CLI client for Ember Cache.

Usage::

    python -m ember_cache.client --host localhost --port 9888

Reads commands from stdin, sends them to the server, prints JSON responses.
Type ``\\quit`` or send EOF (Ctrl-D) to exit.
"""

from __future__ import annotations

import argparse
import contextlib
import socket
import sys


def _repl(host: str, port: int) -> int:
    try:
        sock = socket.create_connection((host, port), timeout=10)
    except OSError as exc:
        print(f"connect error: {exc}", file=sys.stderr)
        return 1

    sock.settimeout(None)
    fileobj = sock.makefile("rwb", buffering=0)
    print(f"connected to {host}:{port} (type \\quit or Ctrl-D to exit)")
    try:
        for line in sys.stdin:
            command = line.strip()
            if not command:
                continue
            if command == "\\quit":
                break
            fileobj.write((command + "\n").encode("utf-8"))
            response = fileobj.readline()
            if not response:
                print("server closed connection", file=sys.stderr)
                return 1
            sys.stdout.write(response.decode("utf-8"))
            sys.stdout.flush()
    finally:
        with contextlib.suppress(OSError):
            sock.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Ember Cache interactive client")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=9888)
    args = parser.parse_args()
    sys.exit(_repl(args.host, args.port))


if __name__ == "__main__":
    main()
