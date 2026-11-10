"""SQL backends, checked against a fake database cursor.

No database is needed: every query the storage and auth backends run is
captured and checked, with SQL injection payloads as the client-supplied
values. (Running them against real databases is covered by the Docker
integration tests.)
"""
import importlib
import re
import sys
import time
import types

import pytest

import settings

EVIL = "x' OR 'a'='a' -- \\"
INJECTED = re.compile(r"'a'\s*=\s*'a'")

STORAGE_BACKENDS = ["storage.mysql", "storage.phorum_mysql", "storage.phorum_pgsql",
                    "storage.phpbb_mysql", "storage.phpnuke_phpbb_mysql"]
AUTH_BACKENDS = ["auth.mysql", "auth.phorum_mysql_users", "auth.phorum_pgsql_users",
                 "auth.phpbb_mysql_users", "auth.phpnuke_phpbb_mysql_users",
                 "auth.postnuke_phpbb_mysql_users"]


class Value(int):
    """Fake column value, usable both as a number and as a string."""
    def strip(self, *args): return "v"
    def split(self, *args): return ["1", "host"]
    def replace(self, *args): return "v"
    def find(self, *args): return -1
    def __len__(self): return 1


class FakeCursor:
    def __init__(self, width):
        self.width = width          # number of columns in every fetched row
        self.statements = []
        self.rowcount = 1
        self.lastrowid = 1

    def execute(self, stmt, params=None):
        self.statements.append((stmt, params))
        return 1

    def fetchone(self):
        return tuple(Value(1) for _ in range(self.width))

    def fetchall(self):
        return [self.fetchone()]

    def insert_id(self):
        return 1


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def autocommit(self, on):
        # MySQLdb style; psycopg2 code assigns 'conn.autocommit = True' instead
        pass

    def cursor(self):
        return self._cursor


@pytest.fixture
def load(monkeypatch):
    """Imports a backend module bound to a fake DB driver; returns
    (module, cursors), where cursors collects every cursor created."""
    cursors = []

    def connect(**kwargs):
        cursor = FakeCursor(load.width)
        cursors.append(cursor)
        return FakeConnection(cursor)

    for name in ("MySQLdb", "psycopg2"):
        monkeypatch.setitem(sys.modules, name, types.SimpleNamespace(connect=connect))
    monkeypatch.setattr(settings, "phorum_settings_path", "/nonexistent/")

    def loader(module_name):
        module = importlib.reload(importlib.import_module(module_name))
        return module, cursors
    load.width = 1
    return loader


def check_statement(stmt, params):
    """Problems with one executed query (an empty list if it's fine)."""
    problems = []
    placeholders = len(re.findall(r"%s", stmt.replace("%%", "")))
    if params is None:
        if placeholders:
            problems.append("%d placeholder(s) but no parameters" % placeholders)
    else:
        if placeholders != len(params):
            problems.append("%d placeholder(s) for %d parameter(s)" % (placeholders, len(params)))
        else:
            stmt % tuple("?" for _ in params)  # raises on a malformed statement
    if INJECTED.search(stmt):
        problems.append("client input reached the SQL text")
    return problems


TS = time.localtime(1_700_000_000)
POST = ("Newsgroups: g\r\nFrom: %s <%s>\r\nSubject: %s\r\nReferences: <1@g>\r\n\r\nbody %s"
        % (EVIL, EVIL, EVIL, EVIL))

# (method, arguments): every client-controlled string is a payload
STORAGE_CALLS = [
    ("group_exists", (EVIL,)),
    ("get_table_name", (EVIL,)),
    ("get_forum", (EVIL,)),
    ("get_GROUP", (EVIL,)),
    ("get_group_stats", (EVIL,)),
    ("get_first_article", (EVIL,)),
    ("article_exists", (EVIL, "range", ("1", "5"))),
    ("get_NEWNEWS", (TS, EVIL)),
    ("get_LIST", (EVIL,)),
    ("get_STAT", (EVIL, "1")),
    ("get_ARTICLE", (EVIL, "1")),
    ("get_HEAD", (EVIL, "1")),
    ("get_BODY", (EVIL, "1")),
    ("get_LAST", (EVIL, "2")),
    ("get_NEXT", (EVIL, "1")),
    ("get_XOVER", (EVIL, "1", "5")),
    ("get_XPAT", (EVIL, "Subject", EVIL, "1", "5")),
    ("get_XPAT", (EVIL, "From", EVIL, "1")),
    ("get_LISTGROUP", (EVIL,)),
    ("get_XGTITLE", (EVIL,)),
    ("get_XGTITLE", ()),
    ("get_XHDR", (EVIL, "Subject", "range", ("1", "5"))),
    ("get_XHDR", (EVIL, "From", "unique", ("1",))),
    ("do_POST", (EVIL, POST, "127.0.0.1", EVIL)),
    ("do_POST", (EVIL, POST, "127.0.0.1", "")),
]


def run(load, module_name, method, args):
    """Runs a backend method with several row shapes (so that whatever the
    code unpacks, some run gets past each fetch) and returns every query."""
    module, cursors = load(module_name)
    for width in range(1, 10):
        load.width = width
        backend = module.Papercut_Storage()
        try:
            getattr(backend, method)(*args)
        except (ValueError, TypeError, IndexError, AttributeError, KeyError, OSError):
            pass  # a row of the wrong shape, or a missing Phorum config file
    return [s for cursor in cursors for s in cursor.statements]


def storage_cases():
    for module_name in STORAGE_BACKENDS:
        for method, args in STORAGE_CALLS:
            yield pytest.param(module_name, method, args, id="%s.%s%s" % (
                module_name.split(".")[1], method, "" if args else "()"))


@pytest.mark.parametrize("module_name, method, args", list(storage_cases()))
def test_storage_queries_are_parameterized(load, module_name, method, args):
    module, _ = load(module_name)
    if not hasattr(module.Papercut_Storage, method):
        pytest.skip("%s has no %s" % (module_name, method))
    statements = run(load, module_name, method, args)
    assert statements, "no queries were executed"
    problems = [(p, stmt) for stmt, params in statements for p in check_statement(stmt, params)]
    assert not problems, "\n\n".join("%s:\n%s" % pair for pair in problems[:3])


BAD_NUMBERS = [
    ("get_ARTICLE", (EVIL, "1 OR 1=1")),
    ("get_HEAD", (EVIL, "1; DROP TABLE x")),
    ("get_XOVER", (EVIL, "1", "5 OR 1=1")),
    ("get_XHDR", (EVIL, "Subject", "range", ("1 OR 1=1",))),
    ("do_POST", (EVIL, POST.replace("<1@g>", "<1 OR 1=1@g>"), "127.0.0.1", "")),
]


@pytest.mark.parametrize("module_name", STORAGE_BACKENDS, ids=lambda m: m.split(".")[1])
@pytest.mark.parametrize("method, args", BAD_NUMBERS, ids=[c[0] for c in BAD_NUMBERS])
def test_non_numeric_article_numbers_are_rejected(load, module_name, method, args):
    module, cursors = load(module_name)
    load.width = 3
    with pytest.raises(ValueError):
        getattr(module.Papercut_Storage(), method)(*args)
    for cursor in cursors:
        for stmt, params in cursor.statements:
            assert "OR 1=1" not in stmt and "DROP" not in stmt


@pytest.mark.parametrize("module_name", [m for m in STORAGE_BACKENDS if m != "storage.mysql"],
                         ids=lambda m: m.split(".")[1])
@pytest.mark.parametrize("header", ["Date", "Message-ID", EVIL])
def test_xpat_only_searches_allowlisted_headers(load, module_name, header):
    module, cursors = load(module_name)
    assert module.Papercut_Storage().get_XPAT("g", header, "*", "1") is None


def test_mysql_xpat_on_date_is_unsupported(load):
    # it used to splice the client's pattern into the query as raw SQL
    module, _ = load("storage.mysql")
    assert module.Papercut_Storage().get_XPAT("g", "Date", "1=1", "1") is None


@pytest.mark.parametrize("module_name", AUTH_BACKENDS, ids=lambda m: m.split(".")[1])
def test_auth_queries_are_parameterized(load, module_name):
    module, cursors = load(module_name)
    module.Papercut_Auth().is_valid_user(EVIL, EVIL)
    (cursor,) = cursors
    assert cursor.statements
    for stmt, params in cursor.statements:
        assert check_statement(stmt, params) == []
        assert params == (EVIL,)


def test_check_statement_catches_problems():
    # the checker itself must be able to fail
    assert check_statement("WHERE name='%s'" % EVIL, None)
    assert check_statement("WHERE a=%s AND b=%s", ("x",))
    assert check_statement("WHERE a=%s", None)
    assert check_statement("WHERE a=%s", ("x",)) == []


class RowsCursor(FakeCursor):
    """Cursor that returns a fixed password hash."""
    def __init__(self, stored):
        super().__init__(1)
        self.stored = stored

    def fetchone(self):
        return (self.stored,)


@pytest.mark.parametrize("module_name", ["auth.phorum_mysql_users", "auth.phorum_pgsql_users"],
                         ids=lambda m: m.split(".")[1])
@pytest.mark.parametrize("password, accepted", [
    ("secret", True),
    ("wrong!", False),
    # regression: glibc's crypt() raises OSError for salt characters outside
    # [a-zA-Z0-9./], and Phorum uses the password's first characters as salt
    ("!secret", False),
    ("'; --", False),
])
def test_phorum_crypt_passwords(load, module_name, password, accepted):
    import crypt
    module, _ = load(module_name)
    auth = module.Papercut_Auth()
    auth.cursor = RowsCursor(crypt.crypt("secret", "se"))
    assert bool(auth.is_valid_user("alice", password)) == accepted


@pytest.mark.parametrize("module_name", ["auth.phorum_mysql_users", "auth.phorum_pgsql_users"],
                         ids=lambda m: m.split(".")[1])
def test_phorum_md5_passwords(load, module_name):
    import hashlib
    module, _ = load(module_name)
    auth = module.Papercut_Auth()
    auth.cursor = RowsCursor(hashlib.md5(b"secret").hexdigest())
    assert auth.is_valid_user("alice", "secret")
    assert not auth.is_valid_user("alice", "wrong")
