"""storage/forwarding_proxy.py, against a fake nntplib (Python 3 API)."""
import collections
import datetime
import importlib
import sys
import time
import types

import pytest

GroupInfo = collections.namedtuple("GroupInfo", "group last first flag")
ArticleInfo = collections.namedtuple("ArticleInfo", "number message_id lines")


class NNTPTemporaryError(Exception):
    pass


class FakeNNTP:
    """Upstream server; records calls and answers like nntplib.NNTP."""

    def __init__(self, host):
        self.host = host
        self.calls = []
        self.groups = {"comp.test": (3, 1, 3)}
        self.posted = None

    def _record(self, *call):
        self.calls.append(call)

    def group(self, name):
        self._record("group", name)
        if name not in self.groups:
            raise NNTPTemporaryError("411 no such group")
        count, first, last = self.groups[name]
        return "211", count, first, last, name

    def list(self, pattern=None):
        self._record("list", pattern)
        return "215", [GroupInfo("comp.test", "3", "1", "y"), GroupInfo("comp.other", "9", "5", "n")]

    def newgroups(self, since):
        self._record("newgroups", since)
        return "231", [GroupInfo("comp.new", "2", "1", "y")]

    def newnews(self, group, since):
        self._record("newnews", group, since)
        return "230", ["<a@x>", "<b@x>"]

    def stat(self, spec):
        self._record("stat", spec)
        if spec == "9":
            raise NNTPTemporaryError("423 no such article")
        return "223", int(spec), "<%s@x>" % spec

    def article(self, spec):
        self._record("article", spec)
        return "220", ArticleInfo(1, "<1@x>", [b"Subject: caf\xc3\xa9", b"From: a@x", b"", b"body", b"line \xff"])

    def head(self, spec):
        self._record("head", spec)
        return "221", ArticleInfo(1, "<1@x>", [b"Subject: hi", b"From: a@x"])

    def body(self, spec):
        self._record("body", spec)
        return "222", ArticleInfo(1, "<1@x>", [b"body", b"more"])

    def over(self, message_spec):
        self._record("over", message_spec)
        return "224", [(1, {"subject": "hi", "from": "a@x", "date": "d", "message-id": "<1@x>",
                            "references": "", ":bytes": "10", ":lines": "2", "xref": None})]

    def _longcmdstring(self, line):
        self._record("_longcmdstring", line)
        return "211", ["1", "2", "3"]

    def descriptions(self, pattern):
        self._record("descriptions", pattern)
        return "215", {"comp.test": "A test group"}

    def xhdr(self, header, spec):
        self._record("xhdr", header, spec)
        return "221", [("1", "hi"), ("2", "there")]

    def post(self, data):
        self._record("post")
        self.posted = data.read()
        return "240 article posted ok"


@pytest.fixture
def proxy(monkeypatch):
    fake = types.SimpleNamespace(NNTP=FakeNNTP, NNTPTemporaryError=NNTPTemporaryError)
    monkeypatch.setitem(sys.modules, "nntplib", fake)
    module = importlib.reload(importlib.import_module("storage.forwarding_proxy"))
    monkeypatch.setattr(module, "log", lambda s: None)
    return module.Papercut_Storage()


def test_connects_to_the_forward_host(proxy):
    import settings
    assert proxy.nntp.host == settings.forward_host


def test_group_exists(proxy):
    assert proxy.group_exists("comp.test") == 1
    assert proxy.group_exists("nope") == 0


def test_group(proxy):
    assert proxy.get_GROUP("comp.test") == (3, 1, 3)


def test_group_stats(proxy):
    # regression: this used to unpack the group name as a (max, min) pair,
    # so LISTGROUP always failed
    assert proxy.get_group_stats("comp.test") == (3, 1, 3, "comp.test")


def test_list(proxy):
    assert proxy.get_LIST() == "comp.test 3 1 y\r\ncomp.other 9 5 n"


def test_newgroups_and_newnews_pass_the_time_as_a_datetime(proxy):
    ts = time.localtime(1_700_000_000)
    assert proxy.get_NEWGROUPS(ts) == "comp.new 2 1 y"
    assert proxy.get_NEWNEWS(ts, "comp.*") == "<a@x>\r\n<b@x>"
    expected = datetime.datetime.fromtimestamp(1_700_000_000)
    assert ("newgroups", expected) in proxy.nntp.calls
    assert ("newnews", "comp.*", expected) in proxy.nntp.calls


def test_stat(proxy):
    assert proxy.get_STAT("comp.test", "2") == 2
    assert proxy.get_STAT("comp.test", "9") is None


def test_article_is_split_into_headers_and_body_and_decoded(proxy):
    headers, body = proxy.get_ARTICLE("comp.test", "1")
    assert headers == "Subject: café\r\nFrom: a@x"
    # bytes that aren't valid UTF-8 survive (and are re-encoded on output)
    assert body == "body\r\nline \udcff"


def test_head_and_body(proxy):
    assert proxy.get_HEAD("comp.test", "1") == "Subject: hi\r\nFrom: a@x"
    assert proxy.get_BODY("comp.test", "1") == "body\r\nmore"


@pytest.mark.parametrize("end, expected_spec", [("5", (1, 5)), ("ggg", (1, None))])
def test_xover(proxy, end, expected_spec):
    assert proxy.get_XOVER("comp.test", "1", end) == "1\thi\ta@x\td\t<1@x>\t\t10\t2\t"
    assert ("over", expected_spec) in proxy.nntp.calls


def test_listgroup(proxy):
    assert proxy.get_LISTGROUP("comp.test") == "1\r\n2\r\n3"
    assert ("_longcmdstring", "LISTGROUP comp.test") in proxy.nntp.calls


def test_xgtitle(proxy):
    assert proxy.get_XGTITLE("comp.*") == "comp.test A test group"


@pytest.mark.parametrize("style, ranges, expected_spec", [
    ("range", ("1", "5"), "1-5"),
    ("range", "12", "12-"),    # regression: used to become "1-2"
    ("unique", "7", "7"),
])
def test_xhdr(proxy, style, ranges, expected_spec):
    assert proxy.get_XHDR("comp.test", "subject", style, ranges) == "1 hi\r\n2 there"
    assert ("xhdr", "subject", expected_spec) in proxy.nntp.calls


def test_post_adds_a_header_and_forwards_bytes(proxy):
    article = "Newsgroups: comp.test\r\nSubject: héllo\r\n\r\nbody ✓"
    assert proxy.do_POST("comp.test", article, "127.0.0.1")
    assert proxy.nntp.posted == (
        "Newsgroups: comp.test\nSubject: héllo\nX-Modified-By: Papercut's forwarding backend\n\nbody ✓"
    ).encode("utf-8")


def test_unsupported_commands(proxy):
    assert proxy.get_XPAT("comp.test", "Subject", "*", "1") is None
    assert proxy.get_NEXT("comp.test", "1") is None
    assert proxy.get_LAST("comp.test", "2") is None
