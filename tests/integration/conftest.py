"""Docker integration tests: the SQL backends against real databases.

Run with:  docker compose -f docker-compose.test.yml run --rm papercut
(see docs/integration-testing-plan.md)
"""
import importlib
import os
import sys
import warnings

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import fakes  # noqa: E402
import papercut  # noqa: E402
import settings  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
MYSQL_HOST = os.environ.get("PAPERCUT_TEST_MYSQL_HOSTS", "")
POSTGRES_HOST = os.environ.get("PAPERCUT_TEST_POSTGRES_HOST", "")


def pytest_collection_modifyitems(items):
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            if not (MYSQL_HOST and POSTGRES_HOST):
                item.add_marker(pytest.mark.skip(reason="needs the Docker test databases"))


def root_connection(kind, database):
    """A privileged connection, for setting up and checking data."""
    if kind == "postgres":
        import psycopg2
        conn = psycopg2.connect(host=POSTGRES_HOST, dbname=database, user="postgres", password="papercut")
        conn.autocommit = True
        return conn
    import MySQLdb
    conn = MySQLdb.connect(host=MYSQL_HOST, db=database, user="root", passwd="papercut", charset="utf8mb4")
    conn.autocommit(True)
    return conn


def query(kind, database, sql, params=None):
    conn = root_connection(kind, database)
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        # lists of tuples, whichever driver
        return [tuple(row) for row in cursor.fetchall()] if cursor.description else None
    finally:
        conn.close()


class Live:
    """A running Papercut server for one backend, plus helpers."""

    def __init__(self, server, backend, kind, database):
        self.server = server
        self.backend = backend
        self.kind = kind
        self.database = database

    @property
    def port(self):
        return self.server.server_address[1]

    def nntp(self, **kwargs):
        # imported here: on Python 3.13+ it comes from standard-nntplib, which
        # only the Docker image installs (collecting these tests mustn't need it)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import nntplib
        return nntplib.NNTP("127.0.0.1", self.port, readermode=False, **kwargs)

    def raw(self):
        return fakes.Client(self.port)

    def query(self, sql, params=None):
        return query(self.kind, self.database, sql, params)


def start_live(monkeypatch, request, storage_module, kind, database, auth_module=None, **extra_settings):
    host = POSTGRES_HOST if kind == "postgres" else MYSQL_HOST
    values = dict(dbhost=host, dbname=database, dbuser="papercut", dbpass="papercut",
                  nntp_hostname="news.example.com",
                  phorum_settings_path=os.path.join(FIXTURES, "phorum_settings") + "/")
    values.update(extra_settings)
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    if kind == "postgres":
        # the PostgreSQL user is the database owner (see the postgres fixtures)
        monkeypatch.setattr(settings, "dbuser", "papercut")
    backend = importlib.import_module(storage_module).Papercut_Storage()
    auth = importlib.import_module(auth_module).Papercut_Auth() if auth_module else None
    server = fakes.start_server(papercut.NNTPRequestHandler, backend, auth)
    request.addfinalizer(server.server_close)
    request.addfinalizer(server.shutdown)
    return Live(server, backend, kind, database)


@pytest.fixture(autouse=True)
def show_server_log():
    """Prints the server log after each test (pytest shows it on failure)."""
    yield
    if os.path.exists(settings.log_file):
        with open(settings.log_file) as f:
            errors = [line for line in f if "Error" in line or "Traceback" in line or line.startswith(("  ", "MySQLdb", "psycopg2"))]
        if errors:
            print("".join(errors))


class MailSink:
    """Collects the messages sent to it over SMTP."""

    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        import email
        import email.policy
        msg = email.message_from_bytes(envelope.content, policy=email.policy.default)
        # decoded headers and body, as a mail client would show them
        text = "".join("%s: %s\n" % item for item in msg.items()) + "\n" + msg.get_content()
        self.messages.append((envelope.mail_from, list(envelope.rcpt_tos), text))
        return "250 OK"


@pytest.fixture
def smtp():
    """An SMTP server on localhost:25, where the Phorum backends send mail."""
    from aiosmtpd.controller import Controller
    sink = MailSink()
    controller = Controller(sink, hostname="127.0.0.1", port=25)
    controller.start()
    yield sink
    controller.stop()
