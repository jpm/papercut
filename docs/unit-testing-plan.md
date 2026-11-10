# Plan: Unit tests

**Status:** in progress (step 1 done)
**Related:** [integration testing plan](integration-testing-plan.md)

## Goal

Papercut has no automated tests. This plan adds fast unit tests that run
without a database or network, to lock in the Python 3 port and the SQL
injection fixes and to make future changes safe.

## Setup

- **Framework:** pytest.
- **Layout:**

  ```
  tests/
    conftest.py          # shared setup
    fakes.py             # fake backend, fake DB cursor, fake NNTP client
    fixtures/            # sample mbox files, maildir trees, MIME messages
    test_strutil.py
    test_mime.py
    test_cache.py
    test_protocol.py
    test_mbox.py
    test_maildir.py
    test_sql_backends.py
    test_forwarding_proxy.py
    integration/         # see integration-testing-plan.md
  ```

- **`conftest.py`:**
  - puts the repo root on `sys.path`
  - points `settings.log_file`, `mbox_path`, `maildir_path` and
    `nntp_cache_path` at temporary directories. `settings.logEvent` otherwise
    writes to `/home/papercut/logs/`.
- **Dependencies:** `requirements-dev.txt` with `pytest`, plus `pytest-cov`
  for coverage reports.
- **Config:** a `[tool.pytest.ini_options]` section in `pyproject.toml`
  registering the `integration` marker, with `-m "not integration"` as the
  default.

## What to test

In priority order.

### 1. `storage/strutil.py`

- `mime_decode_header`:
  - ISO-8859-1 and UTF-8 encoded words
  - `_` decoded as a space
  - several encoded words in one header
  - an unknown charset falls back to latin-1
  - text without encoded words is unchanged
- `format_body`: a line starting with `.` gets a second dot; dots elsewhere
  are untouched.
- `wrap`: wraps at the width, keeps existing newlines, and leaves a word longer
  than the width intact.
- `get_formatted_time`: day of month without a leading zero.
- `format_wildcards` / `format_wildcards_sql`.

### 2. `storage/mime.py`

- `get_text_message` with:
  - a plain-text message
  - a non-MIME message
  - `multipart/alternative` with text and HTML (text wins)
  - an HTML-only multipart message
  - a multipart message with no text part. This currently raises
    `UnboundLocalError`; mark the test `xfail` until it's fixed.
- `get_body`: double dots at the start of a line become single dots.

### 3. Protocol handler (`papercut.py`)

The most valuable tests. Run `NNTPRequestHandler` over a real local socket
(a `socketserver` on port 0 in a thread) with a **fake backend** that records
its calls and returns canned data. Cover:

- **Greeting:** `200` vs `201` depending on `server_type`.
- **Syntax checks for every command:** wrong number of arguments gives `501`;
  unknown commands give `500`; commands are case-insensitive.
- **Required state:** `ARTICLE`, `HEAD`, `BODY`, `STAT`, `XOVER`, `XHDR`,
  `XPAT`, `NEXT` and `LAST` without a selected group give `412`; without a
  selected article, `420`.
- **Article selection:** after `GROUP`, `STAT`/`NEXT`/`LAST` move the current
  article; message-id arguments (`<123@group>`) are converted to numbers.
- **Range parsing:** `XOVER 5`, `5-`, `5-10`; `XHDR` ranges and message-ids.
- **Dates:** `NEWGROUPS`/`NEWNEWS` with 6- and 8-digit dates, with and
  without `GMT`.
- **POST:**
  - read-only server gives `440`
  - an article ends at a line with a single `.`
  - lines are stored without their line endings, and the headers survive
  - an unknown newsgroup gives `441`
  - an exception in the backend gives `441` and is logged
- **AUTHINFO:**
  - the USER then PASS sequence
  - commands are refused (`480`) until login when `nntp_auth` is on
  - **the password is never written to the log**
- **Errors:** an argument that fails `int()` gives `501`; any other backend
  exception gives `503` and a logged traceback; the connection survives both.
- **Timeouts:** with a short handler timeout, an idle connection is closed and
  logged.
- **Encoding:** UTF-8 round-trips, and invalid UTF-8 bytes come back to the
  client exactly as sent.
- **Disconnects:** if the client hangs up mid-session, the handler exits
  cleanly.

### 4. `papercut_cache.py`

- Only methods in `cache_methods` are cached; others always call the backend.
- A second identical call hits the cache; different arguments miss.
- Entries older than `nntp_cache_expire` are refreshed (mock `time.time`).
- Cache file names are stable and contain no path separators.

### 5. `storage/mbox.py` and `storage/maildir.py`

Use temporary fixture mailboxes (built in a fixture, not committed as binary
files).

- **mbox:**
  - numbering and stats, including the quirk that message 0 is skipped
  - group-name case-insensitivity
  - `ARTICLE`/`HEAD`/`BODY`, `XOVER`, `LISTGROUP`, `NEXT`/`LAST` at both ends
  - 8-bit and UTF-8 headers come through intact
- **maildir:**
  - messages in `new/` are moved to `cur/`
  - ordering by timestamp file name
  - `XHDR`/`XPAT` on `MESSAGE-ID`, `XREF`, `BYTES` and `LINES`
  - `POST` writes to `tmp/` and then moves the file to `new/`
  - `NEWNEWS` only returns articles newer than the timestamp

### 6. SQL backends, with a fake cursor (`test_sql_backends.py`)

Make the harness used to check the SQL injection fix a permanent test.
For every method of every SQL storage and auth backend:

- every query's placeholder count matches its parameters
- injection payloads never appear in the SQL text
- non-numeric article numbers raise `ValueError`, which the server turns into
  `501`
- XPAT header allowlists: unsupported headers return `None`

Parametrize over the backends, so a new backend or method automatically gets
covered once it's added to the list.

### 7. `storage/forwarding_proxy.py`

Replace `nntplib.NNTP` with a fake and check that its results are converted
into the format the server expects (CRLF-joined strings, overview fields in
order, decoded bytes).

## Small refactors that make testing easier

Each is optional and can go in its own PR before the tests that need it:

1. **Inject `backend` and `auth`:** these are module-level globals assigned in
   `papercut.py`'s `__main__` block. Making them attributes of the server
   (the handler reads `self.server.backend`) lets tests give each server its
   own fake without patching module globals.
2. **Make `settings` safe to import:** move the `sys.exit()` configuration
   check into a `validate()` function called from `__main__`, so importing
   `settings` can never end the test run.
3. **Split request handling from socket I/O:** pull the line-handling logic
   into a method that takes a line and returns responses. Most protocol tests
   could then skip the socket. Optional; the socket-based tests above work
   without it.

## CI

A GitHub Actions workflow (`.github/workflows/tests.yml`):

- unit tests on Python 3.10, 3.11, 3.12 and 3.13
- installs `requirements-dev.txt` (the DB drivers aren't needed; the fakes
  replace them)
- coverage report as a build artifact
- the Docker integration job from the
  [integration testing plan](integration-testing-plan.md) as a separate job

## Suggested order

One PR each:

1. pytest setup, plus `strutil`, `mime` and cache tests (quick wins that lock
   in the port)
2. refactors 1 and 2, then the protocol handler tests
3. mbox and maildir tests
4. fake-cursor SQL backend tests
5. forwarding proxy tests
6. CI workflow
7. Docker integration tests

## Known bugs these tests will expose

Mark these `xfail` with a reason, and fix them in follow-up PRs:

- `papercut.py` `do_LISTGROUP`: `numbers.split('\r\n')` always returns at
  least one element, so an empty group never resets the current article.

Found and fixed in step 1, with regression tests:

- `storage/strutil.py` `wrap()` looped forever on text with no space after a
  long run of characters. The Phorum backends call it on every posted body,
  so a post ending in a long URL hung the server process.
- `storage/mime.py` returned an empty body for multipart posts (so the
  database backends stored them blank), and raised `UnboundLocalError` when
  there was no text part.
