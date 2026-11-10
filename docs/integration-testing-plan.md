# Plan: Docker integration tests for the database backends

**Status:** proposed
**Related:** [unit testing plan](unit-testing-plan.md), PR #2 (Python 3 port and SQL injection fixes)

## Goal

Run the MySQL and PostgreSQL storage and auth backends against real databases.

After the Python 3 port, these backends have only been tested with a mock
cursor. That proved client input never reaches the SQL text and that
placeholder counts match, but it can't catch SQL a real database rejects,
driver-specific behavior, or differences between MySQL and PostgreSQL.

## Prerequisites

- Docker Desktop (or another Docker engine) running, plus Docker Compose v2.
- On Apple Silicon, `mysql:5.7` has no ARM image and runs under amd64
  emulation (`platform: linux/amd64`). It works but is slow, so it should be an
  optional target.

## 1. Containers

`docker-compose.test.yml` at the repo root:

| Service | Image | Purpose |
| --- | --- | --- |
| `mysql` | `mysql:8.4` | `mysql`, `phorum_mysql`, `phpbb_mysql`, `phpnuke_phpbb_mysql` backends and the MySQL auth modules |
| `mysql57` (optional profile) | `mysql:5.7` | closer to what Phorum and phpBB originally ran on |
| `postgres` | `postgres:16` | `phorum_pgsql` backend and `phorum_pgsql_users` auth |
| `papercut` | built from `tests/docker/Dockerfile` | runs the tests |

The `papercut` image:

- is based on `python:3.13-slim`
- installs build dependencies for `mysqlclient`: `gcc`, `pkg-config`,
  `default-libmysqlclient-dev`
- runs `pip install -r requirements.txt -r requirements-dev.txt`
- mounts the repo at `/src`, so tests run against the working tree

The database services get healthchecks (`mysqladmin ping`, `pg_isready`), and
`papercut` waits on them with `depends_on: condition: service_healthy`.

## 2. Test schemas and data

Store these in `tests/fixtures/sql/` and load them through each database's
`/docker-entrypoint-initdb.d/`.

- **`mysql` backend:** reuse `storage/mysql_storage.sql`.
- **Phorum (MySQL and PostgreSQL):** the repo only has the patch scripts
  (`storage/phorum_*_fix.sql`), not the base tables. Write minimal schemas with
  only the columns the queries use: `forums` (including `nntp_group_name`,
  `table_name`, `description`, `email_list`, `email_return`), and per forum a
  message table, a `<table>_bodies` table and `forums_auth`.
- **phpBB and PHP-Nuke:** minimal `forums`, `posts`, `posts_text`, `topics`,
  `users`, `auth_access` and `user_group` tables, using the configured table
  prefixes (`phpbb_`, `nuke_`, `nuke_bb`).
- **Seed data**, for each backend:
  - two groups with a few articles, including a reply chain (so `References`
    has something to point at) and non-ASCII subjects and bodies
  - one unapproved article (Phorum only), which must never be served
  - one user per auth module, with the password stored the way that app does
    it (MD5 hex, or Phorum's `crypt`)

## 3. Other dependencies of the Phorum backend

- **Phorum config files:** after a post, the Phorum backend reads PHP config
  files from `phorum_settings_path` (`forums.php`, `<forum_id>.php`). Add
  fixture copies under `tests/fixtures/phorum_settings/`.
- **Email:** it also sends moderator notifications through SMTP on
  `localhost` (hardcoded). In the test container, run a small local mail
  catcher (`aiosmtpd`) on port 25 that saves the messages, so tests can check
  the notifications too.

## 4. Configuration

`settings.py` is a module of hardcoded values. Tests load a test settings
module from `tests/` before importing Papercut, with:

- database host, name and credentials pointing at the containers
- `log_file` in a temporary directory
- `phorum_settings_path` pointing at the fixtures
- `nntp_hostname` / `nntp_port` for the test server

The real `settings.py` doesn't change.

## 5. Tests

Location: `tests/integration/`, marked `@pytest.mark.integration` so a plain
`pytest` skips them.

For each storage backend, start the real server (`NNTPServer` +
`NNTPRequestHandler`) on a free port inside the container and talk to it with
`nntplib` (from `standard-nntplib` on Python 3.13+):

- `LIST`, `LIST NEWSGROUPS`, `LIST OVERVIEW.FMT`
- `GROUP`, `LISTGROUP`, `STAT`, `NEXT`, `LAST`
- `ARTICLE` / `HEAD` / `BODY`, by number and by message-id
- `XOVER`, `XHDR`, `XPAT` (Subject, From, and an unsupported header)
- `XGTITLE`, `NEWNEWS`, `NEWGROUPS`
- `POST` a new article and a reply, then read both back. Check threading
  (`References`), non-ASCII content, dot-stuffing, and (Phorum) that the
  notification email was sent.

For each auth module:

- correct password: accepted
- wrong password: rejected
- unknown user: rejected
- injection-style usernames (`' OR '1'='1`, a trailing backslash): rejected,
  with no SQL error

Injection payloads also go through the live server (group names, wildmat
patterns, `References` headers, article numbers like `1 OR 1=1`). Each test
checks the response code, and that row counts and table contents are
unchanged afterwards.

## 6. Running

```sh
docker compose -f docker-compose.test.yml run --rm papercut pytest -m integration
# or
make test-integration
```

**CI:** a GitHub Actions job that runs the same compose file on pull
requests, or nightly if it proves slow. The `mysql57` target runs only in the
nightly job.

## Expected findings

The point of this work is to find problems that only a real database shows.
Some are already visible in the code:

| Backend | Issue |
| --- | --- |
| `mysql` | `COUNT(*) AS check`: `CHECK` is a reserved word since MySQL 8.0.16, so this is a syntax error there |
| `phorum_mysql` | `GROUP BY id` with other columns in the SELECT, which MySQL 5.7+ rejects by default (`ONLY_FULL_GROUP_BY`) |
| `phorum_pgsql` | MySQL-only syntax: `LIMIT 1, 0`, `CURRENT_TIMESTAMP()` with parentheses |
| `phorum_mysql` / `phorum_pgsql` | `get_NEWNEWS` matches the group with `=` against a pattern that uses `%` as a wildcard (it should probably be `LIKE`) |

Fix each one in its own commit, with the integration test that caught it.

## Out of scope

- Performance and load testing
- TLS (`docs/draft-ietf-nntpext-tls-nntp-01.txt`)
- Rewriting the backends; this plan only finds and fixes what's broken
