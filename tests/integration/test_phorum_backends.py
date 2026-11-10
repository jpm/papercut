"""The Phorum storage and auth backends, on MySQL and PostgreSQL."""
import datetime
import io

import pytest

import settings
from conftest import start_live

GROUP = "phorum.test"
EVIL = "x' OR '1'='1"

BACKENDS = {
    "mysql": ("storage.phorum_mysql", "auth.phorum_mysql_users", "mysql"),
    "pgsql": ("storage.phorum_pgsql", "auth.phorum_pgsql_users", "postgres"),
}


@pytest.fixture(params=sorted(BACKENDS))
def live(monkeypatch, request):
    storage, auth, kind = BACKENDS[request.param]
    live = start_live(monkeypatch, request, storage, kind, "phorum", auth_module=auth)
    yield live
    live.query("DELETE FROM forum_1 WHERE id > 4")
    live.query("DELETE FROM forum_1_bodies WHERE id > 4")


def lines_of(info):
    return [l.decode() for l in info.lines]


def test_list(live):
    with live.nntp() as s:
        _, groups = s.list()
    assert [tuple(g) for g in groups] == [(GROUP, "4", "1", "y")]


def test_group_counts_only_approved_messages(live):
    with live.nntp() as s:
        _, count, first, last, name = s.group(GROUP)
    assert (count, first, last, name) == (3, 1, 4, GROUP)


def test_unapproved_messages_are_not_served(live):
    with live.nntp() as s:
        s.group(GROUP)
        with pytest.raises(Exception, match="423"):
            s.article("3")
        _, numbers = s._longcmdstring("LISTGROUP " + GROUP)
    assert numbers == ["1", "2", "4"]


def test_article(live):
    with live.nntp() as s:
        s.group(GROUP)
        _, info = s.article("2")
    lines = lines_of(info)
    assert "From: Bob <bob@example.com>" in lines
    assert "Subject: Re: First post" in lines
    assert "References: <1@%s>" % GROUP in lines
    assert lines[-2:] == ["A reply", ".leading dot"]


def test_non_ascii_content(live):
    with live.nntp() as s:
        s.group(GROUP)
        _, head = s.head("4")
        _, body = s.body("4")
    assert "Subject: Olá mundo" in lines_of(head)
    assert lines_of(body) == ["Corpo com acentuação"]


def test_stat_next_last(live):
    with live.nntp() as s:
        s.group(GROUP)
        assert s.stat("1")[1] == 1
        assert s.next()[1] == 2
        assert s.next()[1] == 4   # 3 is not approved
        assert s.last()[1] == 2


def test_xover(live):
    with live.nntp() as s:
        s.group(GROUP)
        _, overviews = s.over((1, 4))
    assert [n for n, _ in overviews] == [1, 2, 4]
    assert overviews[1][1]["from"] == "Bob <bob@example.com>"
    assert overviews[1][1]["references"] == "<1@%s>" % GROUP


def test_xhdr(live):
    with live.nntp() as s:
        s.group(GROUP)
        _, headers = s.xhdr("subject", "1-4")
    assert headers == [("1", "First post"), ("2", "Re: First post"), ("4", "Olá mundo")]


def test_xpat(live):
    with live.nntp() as s:
        s.group(GROUP)
        _, lines = s._longcmdstring("XPAT Subject 1-4 *First*")
    assert lines == ["1 First post", "2 Re: First post"]


def test_list_newsgroups(live):
    with live.nntp() as s:
        _, descriptions = s.descriptions("phorum.*")
    assert descriptions == {GROUP: "A Phorum test forum"}


def test_newnews(live):
    with live.nntp() as s:
        _, ids = s.newnews(GROUP, datetime.datetime(2024, 1, 2))
    assert ids == ["<2@%s>" % GROUP, "<4@%s>" % GROUP]


def test_post_of_a_new_thread(live, smtp):
    article = ("From: Tester <t@example.com>\r\nNewsgroups: %s\r\nSubject: New thread\r\n\r\nfirst\r\n" % GROUP)
    with live.nntp() as s:
        s.post(io.BytesIO(article.encode()))
        s.group(GROUP)
        _, info = s.article("5")
    lines = lines_of(info)
    assert "Subject: New thread" in lines
    assert not any(line.startswith("References:") for line in lines)
    assert live.query("SELECT thread, parent FROM forum_1 WHERE id = 5") == [(5, 0)]


@pytest.mark.parametrize("subject, body", [
    ("Plain subject", "plain body"),
    ("Assunto com acentuação", "corpo ✓"),
])
def test_post_saves_and_notifies(live, smtp, subject, body):
    article = ("From: Tester <t@example.com>\r\nNewsgroups: %s\r\nSubject: %s\r\n"
               "References: <1@%s>\r\n\r\n%s\r\n" % (GROUP, subject, GROUP, body))
    with live.nntp() as s:
        s.post(io.BytesIO(article.encode()))
        _, count, _, last, _ = s.group(GROUP)
        assert (count, last) == (4, 5)
        _, info = s.article("5")
    lines = lines_of(info)
    assert "Subject: %s" % subject in lines
    assert "References: <1@%s>" % GROUP in lines   # threaded under message 1
    assert lines[-1] == body
    recipients = sorted(r for _, rcpts, _ in smtp.messages for r in rcpts)
    assert recipients == ["list@example.com", "mod@example.com"]
    assert all(body in text for _, _, text in smtp.messages)


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "nntp_auth", "yes")


@pytest.mark.parametrize("username, password, accepted", [
    ("moderator", "secret", True),     # MD5 (newer Phorum)
    ("olduser", "secret", True),       # crypt (older Phorum)
    ("moderator", "wrong", False),
    ("olduser", "!secret", False),
    ("nobody", "secret", False),
    (EVIL.replace(" ", ""), "x", False),
])
def test_login(live, auth_on, username, password, accepted):
    c = live.raw()
    c.cmd("AUTHINFO USER " + username)
    assert c.cmd("AUTHINFO PASS " + password).startswith("281" if accepted else "502")
    c.close()


@pytest.mark.parametrize("command", [
    "GROUP " + EVIL.replace(" ", ""),
    "LISTGROUP " + EVIL.replace(" ", ""),
    "XGTITLE " + EVIL.replace(" ", ""),
    "NEWNEWS " + EVIL.replace(" ", "") + " 20240101 000000",
])
def test_injection_payloads_are_harmless(live, command):
    before = live.query("SELECT COUNT(*) FROM forum_1")
    c = live.raw()
    response = c.cmd(command)
    c.close()
    assert response[:3] in ("211", "230", "282", "411", "481")
    assert live.query("SELECT COUNT(*) FROM forum_1") == before


def test_newnews_with_a_wildcard(live):
    with live.nntp() as s:
        _, ids = s.newnews("phorum.*", datetime.datetime(2024, 1, 2))
    assert ids == ["<2@%s>" % GROUP, "<4@%s>" % GROUP]
