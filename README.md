# Ember Cache — In-Memory Key/Value Datastore with Transactions

A small, single-binary, in-memory key/value server with **all-or-nothing
transactions**, written in Python (asyncio). It speaks a tiny line-based
protocol over a plain TCP socket on port **9888** and returns JSON responses,
so you can drive it with `nc`, `telnet`, or the bundled CLI.

This repository is a take-home solution for the Ember Cache exercise; see
[`_local/Ember_Cache_Home_Assesment.md`](_local/Ember_Cache_Home_Assesment.md)
for the full prompt.

---

## Table of contents

- [Features](#features)
- [Quick start](#quick-start)
- [Manual verification with `nc` and `telnet`](#manual-verification-with-nc-and-telnet)
- [Protocol reference](#protocol-reference)
- [Transaction semantics](#transaction-semantics)
- [Architecture](#architecture)
- [Design choices and assumptions](#design-choices-and-assumptions)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Make targets](#make-targets)
- [Limitations and future work](#limitations-and-future-work)

---

## Features

- Plain TCP server on port `9888`, UTF-8, newline-framed commands.
- JSON responses with the exact field names from the spec
  (`status`, `error_code`, `result`, `mesg`).
- Commands: `PUT`, `GET`, `DEL`, `START`, `COMMIT`, `ROLLBACK`, plus a
  small `PING` extension used for the Docker healthcheck.
- All-or-nothing transactions with **read-committed** isolation.
- Concurrent clients via `asyncio` (one task per connection).
- Dockerfile and `docker-compose.yml`.
- End-to-end test suite (`pytest`) including multi-client and commit-race
  scenarios.
- Interactive CLI client (`python -m ember_cache.client`).
- Smoke script that replays the spec's example sequence.

---

## Quick start

### Option A — Docker (recommended)

```bash
make docker-build
make docker-run        # foreground; Ctrl-C to stop
# or:
make compose-up        # detached
make compose-down
```

The container exposes port `9888` and ships with a `HEALTHCHECK` that issues
a `PING` every 10 s.

### Option B — Local Python (>= 3.12)

```bash
make install           # creates .venv and installs the package + dev deps
make run               # starts the server on 127.0.0.1:9888
```

### Option C — Run the test suite

```bash
make install
make test              # runs the full pytest e2e suite
```

---

## Manual verification with `nc` and `telnet`

The server is intentionally easy to drive by hand.

### Using `nc` (netcat)

In one terminal start the server (`make run` or `make docker-run`), then in
another:

```bash
nc localhost 9888
```

Now type the exact example sequence from the assignment, line by line. The
server response is shown after each command:

```
PUT most_popular_leader georgew
{"status": "Ok"}
START
{"status": "Ok"}
GET most_popular_leader
{"status": "Ok", "result": "georgew"}
PUT georgew {"first_name": "George", "last_name": "Washington", "role": "President"}
{"status": "Ok"}
PUT winstonc {"first_name": "Winston", "last_name": "Churchill", "role": "Prime Minister"}
{"status": "Ok"}
COMMIT
{"status": "Ok"}
GET georgew
{"status": "Ok", "result": "{\"first_name\": \"George\", \"last_name\": \"Washington\", \"role\": \"President\"}"}
PING
{"status": "Ok", "result": "PONG"}
```

> Tip: on macOS use `nc -C localhost 9888` to ensure CRLF is sent;
> on most Linux netcats this is unnecessary because we strip both `\r` and `\n`.

### Using `telnet`

```bash
telnet localhost 9888
Trying 127.0.0.1...
Connected to localhost.
Escape character is '^]'.
PUT hello world
{"status": "Ok"}
GET hello
{"status": "Ok", "result": "world"}
```

To leave: press `Ctrl-]`, then type `quit`.

### Multi-client demo (two terminals)

This shows that uncommitted writes are invisible to other clients and become
visible after `COMMIT`.

Terminal **A**:

```
$ nc localhost 9888
START
{"status": "Ok"}
PUT shared inside_tx
{"status": "Ok"}
```

Terminal **B** (while A has not committed yet):

```
$ nc localhost 9888
GET shared
{"status": "Ok", "result": null}
```

Terminal **A**:

```
COMMIT
{"status": "Ok"}
```

Terminal **B**:

```
GET shared
{"status": "Ok", "result": "inside_tx"}
```

### Scripted smoke test

`make smoke` replays the spec's example sequence and asserts every JSON
response. Requires a server already running on `localhost:9888`:

```bash
make run &        # or: make docker-run &
make smoke
```

### Bundled CLI client

```bash
make client       # python -m ember_cache.client --host 127.0.0.1 --port 9888
```

---

## Protocol reference

### Framing

- Each command is one UTF-8 line terminated by `\n`. `\r\n` is also accepted.
- Each response is one UTF-8 JSON object terminated by `\n`.
- Empty / whitespace-only lines are ignored.
- Commands are case-insensitive (`PUT` and `put` are equivalent).

### Commands

| Command          | Arguments       | Description |
|------------------|-----------------|-------------|
| `PUT key value`  | key + value     | Add or overwrite a value. The *value* is everything after the second whitespace block, so it may contain spaces and JSON literals. |
| `GET key`        | key             | Read a value. Returns `result: null` when the key is unknown. |
| `DEL key`        | key             | Delete a value. Idempotent (no error if missing). |
| `START`          | —               | Begin a transaction on this connection. |
| `COMMIT`         | —               | Atomically apply the transaction's writeset. |
| `ROLLBACK`       | —               | Discard the transaction's writeset. |
| `PING`           | —               | Health-check; returns `result: "PONG"`. |

### Response schema

All responses are JSON objects with these fields:

| Field        | Type             | Notes |
|--------------|------------------|-------|
| `status`     | `"Ok"` / `"Error"` | required |
| `result`     | string or `null` | present on `GET` and `PING`; `null` means cache miss |
| `error_code` | string           | present on errors only |
| `mesg`       | string           | present on errors; optional human-readable hint |

Examples:

```json
{"status": "Ok"}
{"status": "Ok", "result": "some value"}
{"status": "Ok", "result": null}
{"status": "Error", "error_code": "INVALID_ARGS", "mesg": "PUT requires 2 arguments: key and value"}
```

### Error codes

| Code                  | Meaning |
|-----------------------|---------|
| `INVALID_COMMAND`     | Unknown verb. |
| `INVALID_ARGS`        | Wrong number of arguments. |
| `NESTED_TRANSACTION`  | `START` issued while a transaction is already in progress. |
| `NO_TRANSACTION`      | `COMMIT` / `ROLLBACK` issued outside a transaction. |
| `INTERNAL`            | Unexpected server error (logged server-side, connection survives). |

---

## Transaction semantics

Isolation level: **read-committed with atomic commit**.

- Outside a transaction, `PUT` / `DEL` mutate the committed store directly.
  Each is atomic on its own (single-key writeset).
- Inside a transaction, `PUT` / `DEL` are buffered into a per-session
  *writeset*. They are not visible to any other client until `COMMIT`.
- Inside a transaction, `GET` first checks the writeset, then falls back to
  the committed store. So a transaction:
  - sees its own buffered writes, and
  - sees data committed by *other* transactions while this one is in flight
    (read-committed; not snapshot isolation).
- `COMMIT` acquires a global commit lock and applies the entire writeset in
  one critical section — no other client can ever observe a partial commit.
- `ROLLBACK` discards the writeset.
- There is **no write-write conflict detection**. Two concurrent transactions
  modifying the same key produce a *last-commit-wins* outcome. See
  [Limitations](#limitations-and-future-work).

---

## Architecture

```
                +----------------------------+
   client A ----|                            |
                |   asyncio TCP server       |
   client B ----|   (one task per conn)      |
                |                            |
   client N ----|        |                   |
                |        v                   |
                |   Session(writeset?)       |   <-- per-connection state
                |        |                   |
                |        v                   |
                |   commands.handle_line     |
                |        |                   |
                |        v                   |
                |   KVStore                  |
                |   - dict[str, str]         |   <-- committed store
                |   - asyncio.Lock           |   <-- atomicity boundary
                +----------------------------+
```

- `ember_cache.server` — accept loop and per-connection handler.
- `ember_cache.transaction.Session` — buffers a transaction's writeset and
  encodes the read-committed read path.
- `ember_cache.store.KVStore` — committed data; `apply(writeset)` runs under
  `asyncio.Lock` and is the only mutation entry point.
- `ember_cache.protocol` — single source of truth for command parsing and
  JSON response shape.
- `ember_cache.commands` — verb dispatcher.

---

## Design choices and assumptions

1. **Asyncio over threads.** A single event loop scales to thousands of
   idle clients without per-connection thread cost and lets us serialize
   `COMMIT` cheaply with a single `asyncio.Lock`. There is no shared
   mutable state outside the store, so there is no GIL-related contention
   to worry about.
2. **Read-committed instead of snapshot isolation.** The spec only requires
   that committed transactions appear atomically to other clients. Snapshot
   isolation would require cloning the store on `START`, which is wasteful
   for a cache use case. The chosen model matches the spec's "GET inside a
   transaction retrieves the latest committed or the transaction's modified
   value".
3. **Last-commit-wins on conflicting keys.** Conflict detection adds
   complexity and is not required by the prompt. Documented and tested
   explicitly (see `tests/test_commit_race.py`).
4. **Newline-framed protocol.** Easiest to drive with `nc`/`telnet`, which
   the assignment implicitly endorses ("plain socket connection ... UTF-8
   strings"). Length-prefixed framing would have been more general but
   harder to verify by hand.
5. **Values may not contain a literal `\n`.** Callers that need to store
   newline-bearing payloads should JSON-escape them (the spec's own example
   stores a JSON literal as the value, which works).
6. **`GET` on a missing key returns `{"status":"Ok","result":null}`** rather
   than an error. A cache miss is not an error condition, and this matches
   common KV-store behaviour (Redis, memcached).
7. **`DEL` of a missing key is a successful no-op.** Idempotency makes
   client retry logic trivial.
8. **Empty values (`PUT k ""` style) are allowed**; only `PUT k` with no
   value token at all is rejected as `INVALID_ARGS`.
9. **`PING` extension.** Not in the spec, but used by the Docker
   `HEALTHCHECK` and convenient for clients to verify connectivity.
10. **No persistence, no auth, no TLS.** Out of scope for this exercise; the
    server is a pure in-memory cache and is intended to run on a trusted
    network or behind a reverse proxy.
11. **Errors never break the connection.** Any exception while handling a
    command is converted to an `INTERNAL` error response and logged; the
    connection stays open so the client can retry.

---

## Testing

The test suite spins up an in-process server on a random port and drives it
via real TCP connections, so it exercises the full protocol path.

```bash
make test
```

What each file covers:

| File                                | Focus |
|-------------------------------------|-------|
| `tests/test_basic_commands.py`      | PUT/GET/DEL happy path; arg + verb validation; case-insensitive verbs; PING. |
| `tests/test_transactions.py`        | START / COMMIT / ROLLBACK semantics; nested-START and orphan COMMIT errors; the **spec's example sequence** end-to-end. |
| `tests/test_multi_client.py`        | Read-committed visibility; uncommitted writes invisible to peers; per-session transaction independence. |
| `tests/test_commit_race.py`         | 25 concurrent disjoint commits all apply; same-key contention yields one of the two values (never partial); a 50-key transaction is observed atomically by a peer. |

---

## Project layout

```
in-memory-kv-engine/
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── README.md
├── pyproject.toml
├── ember_cache/
│   ├── __init__.py
│   ├── __main__.py        # python -m ember_cache
│   ├── server.py          # asyncio TCP server
│   ├── store.py           # KVStore + atomic apply()
│   ├── transaction.py     # Session + writeset buffering
│   ├── protocol.py        # parse_command, ok/err builders
│   ├── commands.py        # verb dispatcher
│   ├── errors.py          # error codes + CommandError
│   ├── client.py          # interactive CLI
│   └── logging_setup.py
├── scripts/
│   └── smoke.py           # replays the spec's example sequence
└── tests/
    ├── conftest.py
    ├── test_basic_commands.py
    ├── test_transactions.py
    ├── test_multi_client.py
    └── test_commit_race.py
```

---

## Make targets

Run `make` (or `make help`) for the full list. The most useful ones:

| Target           | Description |
|------------------|-------------|
| `make install`   | Create `.venv` and install package + dev dependencies. |
| `make lint`      | `ruff check` + `black --check`. |
| `make format`    | Auto-fix with `ruff` and `black`. |
| `make test`      | Run the pytest suite. |
| `make run`       | Run the server locally. |
| `make client`    | Open the interactive CLI client. |
| `make docker-build` / `make docker-run` | Build/run the container. |
| `make compose-up` / `make compose-down` | docker-compose lifecycle. |
| `make smoke`     | Replay the spec example sequence against a running server. |
| `make clean`     | Remove caches and build artifacts. |

---

## Limitations and future work

- **No persistence.** Data is lost on restart; this is a cache.
- **No write-conflict detection.** Optimistic concurrency control with
  per-key versioning would let the server abort one of two conflicting
  transactions instead of silently accepting last-commit-wins. Easy to add
  on top of `KVStore.apply` (compare a version map under the same lock).
- **No authentication or TLS.** Run behind a trusted boundary.
- **Single process.** Horizontal scaling would require a coordination layer
  (e.g. consistent hashing + a lock service); out of scope here.
- **Newline-framed protocol** means values cannot contain a literal `\n`.
  A length-prefixed framing layer (e.g. `*<len>\n<bytes>\n`) would lift
  this restriction without breaking backwards compatibility for `nc` users.
