"""The 'mysql' storage backend and auth module (storage/mysql_storage.sql)."""
import datetime
import io

import pytest

import settings
from conftest import start_live

GROUP = "papercut.test"
EVIL = "x' OR '1'='1"


@pytest.fixture
def live(monkeypatch, request):
    live = start_live(monkeypatch, request, "storage.mysql", "mysql", "papercut", auth_module="auth.mysql")
    yield live
    live.query("DELETE FROM papercut_default_table WHERE id > 3")


def test_list(live):
    with live.nntp() as s:
        _, groups = s.list()
    assert [tuple(g) for g in groups] == [(GROUP, "3", "1", "y")]


def test_group(live):
    with live.nntp() as s:
        _, count, first, last, name = s.group(GROUP)
    assert (count, first, last, name) == (3, 1, 3, GROUP)


def test_unknown_group(live):
    with live.nntp() as s:
        with pytest.raises(Exception, match="411"):
            s.group("no.such.group")


def test_article_head_and_body(live):
    with live.nntp() as s:
        s.group(GROUP)
        _, info = s.article("2")
        lines = [l.decode() for l in info.lines]
        assert "Subject: Re: First post" in lines
        assert "References: <1@%s>" % GROUP in lines
        assert lines[-2:] == ["Olá, mundo", ".dot"]
        _, head = s.head("1")
        assert "From: Alice" in [l.decode() for l in head.lines]
        _, body = s.body("1")
        assert [l.decode() for l in body.lines] == ["Hello world"]


def test_stat_next_last(live):
    with live.nntp() as s:
        s.group(GROUP)
        assert s.stat("1")[1] == 1
        assert s.next()[1] == 2
        assert s.last()[1] == 1


def test_xover(live):
    with live.nntp() as s:
        s.group(GROUP)
        _, overviews = s.over((1, 3))
    assert [n for n, _ in overviews] == [1, 2, 3]
    assert overviews[1][1]["subject"] == "Re: First post"
    assert overviews[1][1]["references"] == "<1@%s>" % GROUP


def test_xhdr(live):
    with live.nntp() as s:
        s.group(GROUP)
        _, headers = s.xhdr("subject", "1-3")
    assert headers == [("1", "First post"), ("2", "Re: First post"), ("3", "Another thread")]


def test_xpat(live):
    with live.nntp() as s:
        s.group(GROUP)
        _, lines = s._longcmdstring("XPAT Subject 1-3 *First*")
    assert lines == ["1 First post", "2 Re: First post"]


def test_listgroup(live):
    with live.nntp() as s:
        _, lines = s._longcmdstring("LISTGROUP " + GROUP)
    assert lines == ["1", "2", "3"]


def test_list_newsgroups(live):
    with live.nntp() as s:
        _, descriptions = s.descriptions("papercut.*")
    assert descriptions == {GROUP: "Test group"}


def test_newnews(live):
    with live.nntp() as s:
        _, ids = s.newnews(GROUP, datetime.datetime(2024, 1, 2))
    assert ids == ["<2@%s>" % GROUP, "<3@%s>" % GROUP]


def test_post_and_read_back(live):
    article = ("From: Tester <t@example.com>\r\nNewsgroups: %s\r\nSubject: Posted héllo\r\n"
               "References: <1@%s>\r\n\r\nposted body ✓\r\n.dot\r\n" % (GROUP, GROUP))
    with live.nntp() as s:
        s.post(io.BytesIO(article.encode()))
        _, count, first, last, _ = s.group(GROUP)
        assert last == 4
        _, info = s.article("4")
    lines = [l.decode() for l in info.lines]
    assert "Subject: Posted héllo" in lines
    assert "References: <1@%s>" % GROUP in lines
    assert lines[-2:] == ["posted body ✓", ".dot"]


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "nntp_auth", "yes")


@pytest.mark.parametrize("username, password, accepted", [
    ("alice", "secret", True),
    ("alice", "wrong", False),
    ("nobody", "secret", False),
    (EVIL, EVIL, False),
    ("alice\\", "secret", False),
])
def test_login(live, auth_on, username, password, accepted):
    c = live.raw()
    c.cmd("AUTHINFO USER " + username.replace(" ", ""))
    result = c.cmd("AUTHINFO PASS " + password.replace(" ", ""))
    assert result.startswith("281" if accepted else "502")
    c.close()


@pytest.mark.parametrize("command", [
    "GROUP " + EVIL.replace(" ", ""),
    "LISTGROUP " + EVIL.replace(" ", ""),
    "XGTITLE " + EVIL.replace(" ", ""),
    "NEWNEWS " + EVIL.replace(" ", "") + " 20240101 000000",
])
def test_injection_payloads_are_harmless(live, command):
    before = live.query("SELECT COUNT(*) FROM papercut_default_table")
    c = live.raw()
    response = c.cmd(command)
    c.close()
    assert response[:3] in ("211", "230", "282", "411", "481")
    assert live.query("SELECT COUNT(*) FROM papercut_default_table") == before
