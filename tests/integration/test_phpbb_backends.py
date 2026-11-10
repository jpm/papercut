"""The phpBB and PHP-Nuke storage backends, and the phpBB-family auth modules."""
import datetime
import io

import pytest

import settings
from conftest import start_live

EVIL = "x'OR'1'='1"

BACKENDS = {
    "phpbb": dict(storage="storage.phpbb_mysql", auth="auth.phpbb_mysql_users", database="phpbb",
                  group="phpbb.test", prefix="phpbb_", users="phpbb_users",
                  settings=dict(phpbb_table_prefix="phpbb_")),
    "nuke": dict(storage="storage.phpnuke_phpbb_mysql", auth="auth.phpnuke_phpbb_mysql_users", database="nuke",
                 group="nuke.test", prefix="nuke_bb", users="nuke_users",
                 settings=dict(phpbb_table_prefix="nuke_bb", nuke_table_prefix="nuke_")),
}


@pytest.fixture(params=sorted(BACKENDS))
def live(monkeypatch, request):
    config = BACKENDS[request.param]
    live = start_live(monkeypatch, request, config["storage"], "mysql", config["database"],
                      auth_module=config["auth"], **config["settings"])
    live.group = config["group"]
    live.prefix = config["prefix"]
    reset(live, config)
    yield live
    reset(live, config)


def reset(live, config):
    """Back to the fixture data (posts 1-3, topics 1-2)."""
    p = config["prefix"]
    live.query("DELETE FROM %sposts WHERE post_id > 3" % p)
    live.query("DELETE FROM %sposts_text WHERE post_id > 3" % p)
    live.query("DELETE FROM %stopics WHERE topic_id > 2" % p)
    # InnoDB keeps counting after deletes; this resets to MAX(id) + 1
    live.query("ALTER TABLE %sposts AUTO_INCREMENT = 1" % p)
    live.query("ALTER TABLE %stopics AUTO_INCREMENT = 1" % p)
    live.query("UPDATE %sforums SET forum_posts=3, forum_topics=2, forum_last_post_id=3" % p)
    live.query("UPDATE %stopics SET topic_replies=1, topic_last_post_id=2 WHERE topic_id=1" % p)
    live.query("UPDATE %s SET user_posts=2 WHERE user_id=2" % config["users"])


def lines_of(info):
    return [l.decode() for l in info.lines]


def test_list(live):
    with live.nntp() as s:
        _, groups = s.list()
    assert [tuple(g) for g in groups] == [(live.group, "3", "1", "y")]


def test_group(live):
    with live.nntp() as s:
        _, count, first, last, name = s.group(live.group)
    assert (count, first, last, name) == (3, 1, 3, live.group)


def test_article(live):
    with live.nntp() as s:
        s.group(live.group)
        _, info = s.article("2")
    lines = lines_of(info)
    assert "From: alice <alice@example.com>" in lines
    # an empty post subject becomes 'Re: <topic title>'
    assert "Subject: Re: First topic" in lines
    assert "References: <1@%s>" % live.group in lines
    assert lines[-2:] == ["A reply", ".leading dot"]


def test_guest_posts_and_non_ascii(live):
    with live.nntp() as s:
        s.group(live.group)
        _, head = s.head("3")
        _, body = s.body("3")
    head = lines_of(head)
    assert "From: Guest" in head
    assert "Subject: Olá mundo" in head
    assert not any(l.startswith("References:") for l in head)   # first post of its topic
    assert lines_of(body) == ["Corpo com acentuação"]


def test_stat_next_last(live):
    with live.nntp() as s:
        s.group(live.group)
        assert s.stat("1")[1] == 1
        assert s.next()[1] == 2
        assert s.last()[1] == 1


def test_xover(live):
    with live.nntp() as s:
        s.group(live.group)
        _, overviews = s.over((1, 3))
    assert [n for n, _ in overviews] == [1, 2, 3]
    assert overviews[1][1]["subject"] == "Re: First topic"
    assert overviews[1][1]["references"] == "<1@%s>" % live.group
    assert overviews[2][1]["references"] == ""


def test_xhdr(live):
    with live.nntp() as s:
        s.group(live.group)
        _, headers = s.xhdr("subject", "1-3")
    assert headers == [("1", "First topic"), ("2", "Re: First topic"), ("3", "Olá mundo")]


def test_xpat(live):
    with live.nntp() as s:
        s.group(live.group)
        _, lines = s._longcmdstring("XPAT Subject 1-3 *mundo*")
    assert lines == ["3 Olá mundo"]


def test_listgroup(live):
    with live.nntp() as s:
        _, lines = s._longcmdstring("LISTGROUP " + live.group)
    assert lines == ["1", "2", "3"]


def test_list_newsgroups(live):
    with live.nntp() as s:
        _, descriptions = s.descriptions("*")
    assert list(descriptions) == [live.group]


def test_newnews(live):
    with live.nntp() as s:
        _, ids = s.newnews(live.group, datetime.datetime(2024, 1, 2))
    assert ids == ["<2@%s>" % live.group, "<3@%s>" % live.group]


def post(live, subject, body, references=None):
    lines = ["From: Tester <t@example.com>", "Newsgroups: " + live.group, "Subject: " + subject]
    if references:
        lines.append("References: " + references)
    article = "\r\n".join(lines) + "\r\n\r\n" + body + "\r\n"
    with live.nntp() as s:
        s.post(io.BytesIO(article.encode()))
        _, count, _, last, _ = s.group(live.group)
        _, info = s.article(str(last))
    return count, last, lines_of(info)


def test_post_a_new_topic(live):
    count, last, lines = post(live, "Novo tópico", "corpo ✓")
    assert (count, last) == (4, 4)
    assert "Subject: Novo tópico" in lines
    assert lines[-1] == "corpo ✓"
    topic = live.query("SELECT topic_id, topic_title FROM %stopics WHERE topic_first_post_id = 4" % live.prefix)
    assert topic == [(3, "Novo tópico")]


def test_post_a_reply(live):
    count, last, lines = post(live, "Re: First topic", "a reply", references="<1@%s>" % live.group)
    assert (count, last) == (4, 4)
    assert "References: <1@%s>" % live.group in lines
    assert live.query("SELECT topic_id FROM %sposts WHERE post_id = 4" % live.prefix) == [(1,)]
    assert live.query("SELECT topic_replies, topic_last_post_id FROM %stopics WHERE topic_id = 1" % live.prefix) == [(2, 4)]


@pytest.fixture
def auth_on(monkeypatch):
    monkeypatch.setattr(settings, "nntp_auth", "yes")


@pytest.mark.parametrize("username, password, accepted", [
    ("alice", "secret", True),
    ("alice", "wrong", False),
    ("nobody", "secret", False),
    (EVIL, EVIL, False),
])
def test_login(live, auth_on, username, password, accepted):
    c = live.raw()
    c.cmd("AUTHINFO USER " + username)
    assert c.cmd("AUTHINFO PASS " + password).startswith("281" if accepted else "502")
    c.close()


def test_postnuke_login(monkeypatch, request, auth_on):
    live = start_live(monkeypatch, request, "storage.phpbb_mysql", "mysql", "postnuke",
                      auth_module="auth.postnuke_phpbb_mysql_users")
    for username, password, accepted in [("alice", "secret", True), ("alice", "nope", False), (EVIL, "x", False)]:
        c = live.raw()
        c.cmd("AUTHINFO USER " + username)
        assert c.cmd("AUTHINFO PASS " + password).startswith("281" if accepted else "502")
        c.close()


@pytest.mark.parametrize("command", ["GROUP " + EVIL, "LISTGROUP " + EVIL, "XGTITLE " + EVIL,
                                     "NEWNEWS " + EVIL + " 20240101 000000"])
def test_injection_payloads_are_harmless(live, command):
    before = live.query("SELECT COUNT(*) FROM %sposts" % live.prefix)
    c = live.raw()
    response = c.cmd(command)
    c.close()
    assert response[:3] in ("211", "230", "282", "411", "481")
    assert live.query("SELECT COUNT(*) FROM %sposts" % live.prefix) == before


def test_xrover(live):
    # only post 2 is a reply; post 3 starts topic 2 (the topic id used to be
    # reported as the replied-to article)
    with live.nntp() as s:
        s.group(live.group)
        _, lines = s._longcmdstring("XROVER 1-3")
    assert lines == ["2 <1@%s>" % live.group]
