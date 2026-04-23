"""Smoke test: reproduce the assignment's example sequence against a live server.

Exits 0 on success, 1 on the first mismatch. Intended for ``make smoke`` after
``make docker-run`` (or ``make run``).
"""

from __future__ import annotations

import argparse
import json
import socket
import sys

GEORGE = '{"first_name": "George", "last_name": "Washington", "role": "President"}'
WINSTON = '{"first_name": "Winston", "last_name": "Churchill", "role": "Prime Minister"}'

# (command, expected_response)
SCRIPT: list[tuple[str, dict]] = [
    ("PUT most_popular_leader georgew", {"status": "Ok"}),
    ("START", {"status": "Ok"}),
    ("GET most_popular_leader", {"status": "Ok", "result": "georgew"}),
    (f"PUT georgew {GEORGE}", {"status": "Ok"}),
    (f"PUT winstonc {WINSTON}", {"status": "Ok"}),
    ("COMMIT", {"status": "Ok"}),
    ("GET georgew", {"status": "Ok", "result": GEORGE}),
    ("GET winstonc", {"status": "Ok", "result": WINSTON}),
    ("PING", {"status": "Ok", "result": "PONG"}),
]


def run(host: str, port: int) -> int:
    try:
        sock = socket.create_connection((host, port), timeout=5)
    except OSError as exc:
        print(f"connect error: {exc}", file=sys.stderr)
        return 1

    f = sock.makefile("rwb", buffering=0)
    failures = 0
    try:
        for command, expected in SCRIPT:
            f.write((command + "\n").encode("utf-8"))
            line = f.readline()
            if not line:
                print("server closed connection", file=sys.stderr)
                return 1
            actual = json.loads(line.decode("utf-8"))
            ok = actual == expected
            mark = "OK " if ok else "FAIL"
            print(f"[{mark}] {command}")
            print(f"       got: {actual}")
            if not ok:
                print(f"  expected: {expected}")
                failures += 1
    finally:
        sock.close()

    if failures:
        print(f"\n{failures} mismatch(es)", file=sys.stderr)
        return 1
    print("\nAll smoke checks passed.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9888)
    args = parser.parse_args()
    sys.exit(run(args.host, args.port))


if __name__ == "__main__":
    main()
