"""Tests for the NNTP protocol handler (papercut.NNTPRequestHandler).

Each test runs the real handler on a local socket, with a fake storage
backend that records its calls.
"""
import calendar
import os
import re
import time

import pytest

import fakes
import papercut
import settings


@pytest.fixture
def backend():
    return fakes.FakeBackend()


@pytest.fixture
def auth():
    return fakes.FakeAuth({"alice": "s3cret"})


@pytest.fixture(scope="module")
def shared_server():
    srv = fakes.start_server(papercut.NNTPRequestHandler, None)
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def server(shared_server, backend, auth):
    """The shared server, with this test's own fake backend and auth."""
    shared_server.backend = backend
    shared_server.auth = auth
    return shared_server


@pytest.fixture
def client(server):
    c = fakes.Client(server.server_address[1])
    yield c
    c.close()


@pytest.fixture
def connect(server):
    """Factory for extra clients (e.g. after changing settings)."""
    clients = []

    def make():
        c = fakes.Client(server.server_address[1])
        clients.append(c)
        return c
    yield make
    for c in clients:
        c.close()


def log_text():
    if not os.path.exists(settings.log_file):
        return ""
    with open(settings.log_file) as f:
        return f.read()


def wait_for_log(text, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if text in log_text():
            return True
        time.sleep(0.02)
    return False


def code(response):
    return response.split(" ", 1)[0]


# --- greeting and general command handling ---

def test_greeting_allows_posting_on_a_read_write_server(client):
    assert client.greeting.startswith("200 %s Papercut %s" % (settings.nntp_hostname, papercut.__VERSION__))


def test_greeting_on_a_read_only_server(monkeypatch, connect):
    monkeypatch.setattr(settings, "server_type", "read-only")
    assert code(connect().greeting) == "201"


def test_unknown_command(client):
    assert code(client.cmd("FROBNICATE")) == "500"


def test_commands_are_case_insensitive(client, backend):
    assert code(client.cmd("group test.group")) == "211"
    assert code(client.cmd("Stat 1")) == "223"


def test_quit_says_goodbye_and_closes_the_connection(client):
    assert code(client.cmd("QUIT")) == "205"
    assert client.readline_bytes() == b""


def test_help_lists_the_commands(client):
    assert code(client.cmd("HELP")) == "100"
    lines = [line.strip() for line in client.read_multiline()]
    assert "ARTICLE" in lines and "XOVER" in lines


def test_date(client):
    assert re.fullmatch(r"111 \d{14}", client.cmd("DATE"))


def test_xversion(client):
    assert client.cmd("XVERSION") == "200 Papercut %s" % papercut.__VERSION__


@pytest.mark.parametrize("server_type, expected", [("read-write", "200"), ("read-only", "201")])
def test_mode_reader(monkeypatch, client, server_type, expected):
    monkeypatch.setattr(settings, "server_type", server_type)
    assert code(client.cmd("MODE READER")) == expected


def test_mode_stream_is_not_supported(client):
    assert code(client.cmd("MODE STREAM")) == "500"


def test_slave(client):
    assert code(client.cmd("SLAVE")) == "202"


def test_ihave_is_refused(client):
    assert code(client.cmd("IHAVE <1@test.group>")) == "435"
    assert code(client.cmd("IHAVE nonsense")) == "501"


def test_connection_is_closed_after_ten_empty_lines(client):
    for _ in range(10):
        client.send("")
    assert client.readline_bytes() == b""


# --- group and article selection ---

def test_group_selects_the_group(client, backend):
    assert client.cmd("GROUP test.group") == "211 3 1 3 test.group group selected"
    assert backend.called("get_GROUP") == [("test.group",)]


def test_group_that_does_not_exist(client, backend):
    backend.returns["group_exists"] = False
    assert code(client.cmd("GROUP nope")) == "411"


def test_group_needs_exactly_one_argument(client):
    assert code(client.cmd("GROUP")) == "501"
    assert code(client.cmd("GROUP a b")) == "501"


@pytest.mark.parametrize("command", [
    "ARTICLE 1", "HEAD 1", "BODY 1", "STAT 1", "NEXT", "LAST", "XOVER 1-2", "XHDR subject 1-2",
])
def test_article_commands_need_a_selected_group(client, command):
    assert code(client.cmd(command)) == "412"


@pytest.mark.parametrize("command", ["HEAD", "BODY", "STAT", "LAST", "XOVER", "XHDR subject"])
def test_commands_without_an_article_need_a_current_article(client, command):
    client.cmd("GROUP test.group")
    assert code(client.cmd(command)) == "420"


def test_article_by_number(client, backend):
    client.cmd("GROUP test.group")
    assert client.cmd("ARTICLE 1") == "220 1 <1@test.group> All of the article follows"
    assert client.read_multiline() == ["Subject: hello", "From: someone", "", "body text"]
    assert backend.called("get_ARTICLE") == [("test.group", "1")]


def test_article_by_message_id_uses_the_number_in_it(client, backend):
    client.cmd("GROUP test.group")
    assert code(client.cmd("ARTICLE <7@test.group>")) == "220"
    client.read_multiline()
    assert backend.called("get_ARTICLE") == [("test.group", "7")]


def test_article_that_does_not_exist(client, backend):
    backend.returns["get_ARTICLE"] = None
    client.cmd("GROUP test.group")
    assert code(client.cmd("ARTICLE 99")) == "423"


def test_head_and_body(client, backend):
    client.cmd("GROUP test.group")
    assert code(client.cmd("HEAD 1")) == "221"
    assert client.read_multiline() == ["Subject: hello", "From: someone"]
    assert code(client.cmd("BODY 1")) == "222"
    assert client.read_multiline() == ["body text"]


def test_head_and_body_use_the_current_article(client, backend):
    client.cmd("GROUP test.group")
    client.cmd("STAT 2")
    client.cmd("HEAD")
    client.read_multiline()
    client.cmd("BODY")
    client.read_multiline()
    assert backend.called("get_HEAD") == [("test.group", "2")]
    assert backend.called("get_BODY") == [("test.group", "2")]


def test_stat_sets_the_current_article(client, backend):
    client.cmd("GROUP test.group")
    assert client.cmd("STAT 2") == "223 2 <1@test.group> article retrieved - request text separately"
    assert code(client.cmd("STAT")) == "223"
    assert backend.called("get_STAT") == [("test.group", "2"), ("test.group", "2")]


def test_stat_of_a_missing_article(client, backend):
    backend.returns["get_STAT"] = False
    client.cmd("GROUP test.group")
    assert code(client.cmd("STAT 99")) == "423"


def test_next_without_a_current_article_starts_at_the_first(client, backend):
    client.cmd("GROUP test.group")
    assert code(client.cmd("NEXT")) == "223"
    assert backend.called("get_first_article") == [("test.group",)]


def test_next_and_last_move_the_current_article(client, backend):
    client.cmd("GROUP test.group")
    client.cmd("STAT 1")
    assert client.cmd("NEXT").startswith("223 2 ")
    assert backend.called("get_NEXT") == [("test.group", "1")]
    assert client.cmd("LAST").startswith("223 1 ")
    assert backend.called("get_LAST") == [("test.group", 2)]


def test_next_and_last_at_the_ends_of_the_group(client, backend):
    backend.returns["get_NEXT"] = None
    backend.returns["get_LAST"] = None
    client.cmd("GROUP test.group")
    client.cmd("STAT 1")
    assert code(client.cmd("NEXT")) == "421"
    assert code(client.cmd("LAST")) == "422"


# --- ranges ---

@pytest.mark.parametrize("command, expected_args", [
    ("XOVER 5", ("test.group", "5", "5")),
    ("XOVER 5-", ("test.group", "5")),
    ("XOVER 5-10", ("test.group", "5", "10")),
    ("OVER 5-10", ("test.group", "5", "10")),
])
def test_xover_ranges(client, backend, command, expected_args):
    client.cmd("GROUP test.group")
    assert code(client.cmd(command)) == "224"
    client.read_multiline()
    assert backend.called("get_XOVER") == [expected_args]


def test_xover_with_no_results(client, backend):
    backend.returns["get_XOVER"] = ""
    client.cmd("GROUP test.group")
    assert code(client.cmd("XOVER 1-2")) == "224"
    assert client.read_multiline() == []


@pytest.mark.parametrize("command, expected_args", [
    ("XHDR subject 5-", ("test.group", "subject", "range", "5")),
    ("XHDR from 5-10", ("test.group", "from", "range", ("5", "10"))),
    ("XHDR subject <7@test.group>", ("test.group", "subject", "unique", "7")),
    ("HDR subject 5-10", ("test.group", "subject", "range", ("5", "10"))),
])
def test_xhdr_ranges(client, backend, command, expected_args):
    client.cmd("GROUP test.group")
    assert code(client.cmd(command)) == "221"
    client.read_multiline()
    assert backend.called("get_XHDR") == [expected_args]


def test_xhdr_supports_subject_from_and_references(client):
    client.cmd("GROUP test.group")
    assert code(client.cmd("XHDR date 1-2")) == "501"
    assert code(client.cmd("XHDR references 1-2")) == "221"
    client.read_multiline()


def test_xhdr_with_no_results_sends_an_empty_list(client, backend):
    backend.returns["get_XHDR"] = ""
    client.cmd("GROUP test.group")
    assert code(client.cmd("XHDR subject 1-2")) == "221"
    assert client.read_multiline() == []


@pytest.mark.parametrize("command, expected_args", [
    ("XROVER 1-5", ("test.group", "REFERENCES", "range", ("1", "5"))),
    ("XROVER 3-", ("test.group", "REFERENCES", "range", "3")),
    ("XROVER", ("test.group", "REFERENCES", "unique", "2")),
])
def test_xrover_is_xhdr_references(client, backend, command, expected_args):
    # regression: XROVER overwrote its range argument with the header name,
    # and XHDR then refused REFERENCES, so XROVER always failed
    client.cmd("GROUP test.group")
    client.cmd("STAT 2")
    assert code(client.cmd(command)) == "221"
    client.read_multiline()
    assert backend.called("get_XHDR") == [expected_args]


def test_xrover_needs_a_group(client):
    assert code(client.cmd("XROVER 1-5")) == "412"


def test_xpat(client, backend):
    client.cmd("GROUP test.group")
    assert code(client.cmd("XPAT Subject 1-5 *hello*")) == "221"
    assert client.read_multiline() == ["1 hello"]
    assert backend.called("get_XPAT") == [("test.group", "Subject", "*hello*", "1", "5")]


def test_xpat_on_an_unknown_header_returns_nothing(client, backend):
    client.cmd("GROUP test.group")
    assert code(client.cmd("XPAT X-Unknown 1-5 *")) == "221"
    assert client.read_multiline() == []
    assert backend.called("get_XPAT") == []


# --- listing commands ---

def test_list(client, backend):
    assert code(client.cmd("LIST")) == "215"
    assert client.read_multiline() == ["test.group 3 1 y"]
    assert backend.called("get_LIST") == [("",)]


def test_list_overview_fmt(client):
    assert code(client.cmd("LIST OVERVIEW.FMT")) == "215"
    assert client.read_multiline() == [h + ":" for h in papercut.overview_headers]


def test_list_extensions(client):
    assert code(client.cmd("LIST EXTENSIONS")) == "215"
    assert "XOVER" in client.read_multiline()


def test_list_newsgroups(client, backend):
    assert code(client.cmd("LIST NEWSGROUPS comp.*")) == "215"
    assert client.read_multiline() == ["test.group A test group"]
    assert backend.called("get_XGTITLE") == [("comp.*",)]


def test_list_with_an_unsupported_keyword(client):
    assert code(client.cmd("LIST ACTIVE.TIMES")) == "503"


def test_listgroup_selects_the_group_and_its_first_article(client, backend):
    assert client.cmd("LISTGROUP test.group").startswith("211 3 1 3 test.group")
    assert client.read_multiline() == ["1", "2", "3"]
    assert code(client.cmd("HEAD")) == "221"
    client.read_multiline()
    assert backend.called("get_HEAD") == [("test.group", "1")]


def test_listgroup_of_a_missing_group(client, backend):
    backend.returns["group_exists"] = False
    assert code(client.cmd("LISTGROUP nope")) == "411"


def test_listgroup_without_a_group(client):
    assert code(client.cmd("LISTGROUP")) == "412"


def test_listgroup_of_an_empty_group_clears_the_current_article(client, backend):
    # regression: ''.split('\r\n') is [''], so an empty group used to make ''
    # the current article
    backend.returns["get_LISTGROUP"] = ""
    client.cmd("GROUP test.group")
    client.cmd("STAT 2")
    assert code(client.cmd("LISTGROUP test.group")) == "211"
    # regression: an empty list used to be sent as one blank line
    assert client.read_multiline() == []
    assert code(client.cmd("STAT")) == "420"


def test_listgroup_selects_an_empty_group(client, backend):
    client.cmd("GROUP test.group")
    backend.returns["get_LISTGROUP"] = ""
    backend.returns["get_group_stats"] = (0, 0, 0, "empty.group")
    assert client.cmd("LISTGROUP empty.group").startswith("211 0 0 0 empty.group")
    client.read_multiline()
    assert backend.called("get_group_stats") == [("empty.group",)]
    client.cmd("XOVER 1-2")
    client.read_multiline()
    assert backend.called("get_XOVER")[0][0] == "empty.group"


def test_xgtitle(client, backend):
    assert code(client.cmd("XGTITLE comp.*")) == "282"
    assert client.read_multiline() == ["test.group A test group"]


def test_xgtitle_when_descriptions_are_unavailable(client, backend):
    backend.returns["get_XGTITLE"] = None
    assert code(client.cmd("XGTITLE comp.*")) == "481"


# --- NEWGROUPS / NEWNEWS date parsing ---

@pytest.mark.parametrize("date, year", [("20240105", 2024), ("240105", 2024), ("990105", 1999)])
def test_newgroups_parses_the_date(client, backend, date, year):
    assert code(client.cmd("NEWGROUPS %s 093000" % date)) == "231"
    assert client.read_multiline() == []
    (ts,), = backend.called("get_NEWGROUPS")
    assert (ts.tm_year, ts.tm_mon, ts.tm_mday) == (year, 1, 5)


@pytest.mark.parametrize("date", ["20240105", "240105", "20240705"])
def test_newgroups_dates_are_local_time_by_default(client, backend, date):
    # regression: 8-digit dates used to read the month and day at the
    # wrong offsets (20240105 became December 2025)
    client.cmd("NEWGROUPS %s 093000" % date)
    client.read_multiline()
    (ts,), = backend.called("get_NEWGROUPS")
    month = int(date[-4:-2])
    assert time.mktime(ts) == time.mktime((2024, month, 5, 9, 30, 0, 0, 0, -1))


@pytest.mark.parametrize("date", ["20240105", "20240705"])
def test_newgroups_with_gmt_reads_the_time_as_gmt(client, backend, date):
    # regression: GMT times used to be read as local time
    client.cmd("NEWGROUPS %s 093000 GMT" % date)
    client.read_multiline()
    (ts,), = backend.called("get_NEWGROUPS")
    month = int(date[4:6])
    assert time.mktime(ts) == calendar.timegm((2024, month, 5, 9, 30, 0, 0, 0, 0))


def test_newgroups_syntax(client):
    assert code(client.cmd("NEWGROUPS 20240105")) == "501"


def test_newnews(client, backend):
    backend.returns["get_NEWNEWS"] = "<1@test.group>\r\n<2@test.group>"
    assert code(client.cmd("NEWNEWS test.group 20240105 000000")) == "230"
    assert client.read_multiline() == ["<1@test.group>", "<2@test.group>"]
    ts, group = backend.called("get_NEWNEWS")[0]
    assert group == "test.group" and ts.tm_year == 2024


def test_newnews_for_a_missing_group(client, backend):
    backend.returns["group_exists"] = False
    assert code(client.cmd("NEWNEWS nope 20240105 000000")) == "411"


# --- POST ---

ARTICLE_LINES = [
    "Newsgroups: test.group",
    "From: Tester <t@example.com>",
    "Subject: héllo",
    "",
    "first line",
    "..dot-stuffed",
    "",
    "last line",
]


def post(client, lines=ARTICLE_LINES):
    assert code(client.cmd("POST")) == "340"
    for line in lines:
        client.send(line)
    return client.cmd(".")


def test_post_passes_the_article_to_the_backend(client, backend):
    assert code(post(client)) == "240"
    (group, text, ip, username), = backend.called("do_POST")
    assert group == "test.group"
    # regression: lines used to keep their CRLF and were then joined with
    # another CRLF, so every line was followed by a blank one
    assert text == "\r\n".join(ARTICLE_LINES)
    assert ip == "127.0.0.1" and username == ""


def test_post_to_an_unknown_group(client, backend):
    backend.returns["group_exists"] = False
    assert code(post(client)) == "441"
    assert backend.called("do_POST") == []


def test_post_rejected_by_the_backend(client, backend):
    backend.returns["do_POST"] = None
    assert code(post(client)) == "441"


def test_post_backend_exception_is_reported_and_logged(client, backend):
    backend.returns["do_POST"] = RuntimeError("database is down")
    assert code(post(client)) == "441"
    assert wait_for_log("database is down")
    # the connection is still usable
    assert code(client.cmd("DATE")) == "111"


def test_post_on_a_read_only_server(monkeypatch, client):
    monkeypatch.setattr(settings, "server_type", "read-only")
    assert code(client.cmd("POST")) == "440"


def test_post_requires_authentication_when_enabled(monkeypatch, client):
    monkeypatch.setattr(settings, "nntp_auth", "yes")
    assert code(client.cmd("POST")) == "480"


# --- AUTHINFO ---

@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "nntp_auth", "yes")


def test_commands_are_refused_until_login(auth_on, client):
    assert code(client.cmd("GROUP test.group")) == "480"
    assert code(client.cmd("MODE READER")) == "200"


def test_login(auth_on, client, auth, backend):
    assert code(client.cmd("AUTHINFO USER alice")) == "381"
    assert code(client.cmd("AUTHINFO PASS s3cret")) == "281"
    assert auth.calls == [("alice", "s3cret")]
    assert code(client.cmd("GROUP test.group")) == "211"
    client.cmd("LIST")
    client.read_multiline()
    assert backend.called("get_LIST") == [("alice",)]


def test_login_with_a_wrong_password(auth_on, client):
    client.cmd("AUTHINFO USER alice")
    assert code(client.cmd("AUTHINFO PASS wrong")) == "502"
    assert code(client.cmd("GROUP test.group")) == "480"


def test_authinfo_needs_two_arguments(client):
    assert code(client.cmd("AUTHINFO USER")) == "501"


def test_authinfo_is_accepted_when_auth_is_off(client):
    assert code(client.cmd("AUTHINFO USER anyone")) == "281"


@pytest.mark.parametrize("command", ["AUTHINFO PASS s3cret", "authinfo pass s3cret", "AuthInfo Pass s3cret"])
def test_passwords_are_never_logged(auth_on, client, command):
    client.cmd("AUTHINFO USER alice")
    client.cmd(command)
    client.cmd("QUIT")
    assert wait_for_log("Connection closed")
    assert "s3cret" not in log_text()


# --- errors, timeouts, encoding ---

def test_non_numeric_article_numbers_are_a_syntax_error(client, backend):
    backend.returns["get_ARTICLE"] = ValueError("invalid literal for int()")
    client.cmd("GROUP test.group")
    assert code(client.cmd("ARTICLE abc")) == "501"
    assert code(client.cmd("DATE")) == "111"


def test_backend_errors_are_reported_and_logged(client, backend):
    backend.returns["get_LIST"] = RuntimeError("boom")
    assert code(client.cmd("LIST")) == "503"
    assert wait_for_log("RuntimeError: boom")
    assert code(client.cmd("DATE")) == "111"


def test_missing_arguments_are_a_syntax_error(client):
    assert code(client.cmd("MODE")) == "501"


def test_idle_connections_time_out(backend, auth):
    class QuickTimeout(papercut.NNTPRequestHandler):
        timeout = 0.3
    srv = fakes.start_server(QuickTimeout, backend, auth)
    try:
        c = fakes.Client(srv.server_address[1])
        assert c.readline_bytes() == b""  # closed by the server
        assert wait_for_log("Connection timed out")
        c.close()
    finally:
        srv.shutdown()
        srv.server_close()


def test_utf8_round_trips(client, backend):
    backend.returns["get_GROUP"] = (1, 1, 1)
    assert client.cmd("GROUP café") == "211 1 1 1 café group selected"
    assert backend.called("group_exists") == [("café",)]


def test_invalid_utf8_bytes_round_trip_unchanged(client, backend):
    backend.returns["get_GROUP"] = (1, 1, 1)
    client.send(b"GROUP caf\xe9")
    assert client.readline_bytes() == b"211 1 1 1 caf\xe9 group selected\r\n"


def test_client_disconnect_mid_session_is_handled(client):
    client.cmd("GROUP test.group")
    client.close()
    assert wait_for_log("Connection closed")


@pytest.mark.parametrize("pattern", ["comp.*", "*", "comp.lang.?", "comp.*,!comp.test"])
def test_newnews_accepts_wildmat_patterns(client, backend, pattern):
    # regression: any group argument other than '*' had to be an existing
    # group, so wildmats like comp.* were refused with 411
    backend.returns["group_exists"] = False
    assert code(client.cmd("NEWNEWS %s 20240105 000000" % pattern)) == "230"
    client.read_multiline()
    assert backend.called("get_NEWNEWS")[0][1] == pattern
