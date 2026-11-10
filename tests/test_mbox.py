import os

import pytest

import settings
from storage import mbox

GROUP = "papercut.mbox.test"

MBOX = """\
From a@b Mon Jan  1 00:00:00 2024
From: Placeholder <zero@example.com>
Subject: not served
Message-ID: <0@example.com>

the first message in the file is skipped
From a@b Mon Jan  1 00:00:00 2024
From: =?iso-8859-1?q?Jo=E3o?= <jpm@example.com>
Subject: Olá mundo
Date: Mon, 1 Jan 2024 00:00:00 +0000
Message-ID: <1@example.com>

first body
.leading dot
From a@b Mon Jan  1 00:00:00 2024
From: Two <two@example.com>
Subject: second
Date: Tue, 2 Jan 2024 00:00:00 +0000
Message-ID: <2@example.com>
In-Reply-To: <1@example.com>

second body
"""


@pytest.fixture
def storage():
    with open(os.path.join(settings.mbox_path, "test"), "w", encoding="utf-8") as f:
        f.write(MBOX)
    return mbox.Papercut_Storage()


def test_each_file_is_a_group(storage):
    assert storage.get_group_list() == [GROUP]
    assert storage.group_exists(GROUP)
    assert storage.group_exists(GROUP.upper())
    assert not storage.group_exists("papercut.mbox.other")


def test_group_range_matches_the_served_articles(storage):
    # regression: the last article was reported as 3, which doesn't exist
    assert storage.get_GROUP(GROUP) == (2, 1, 2)
    assert storage.get_group_stats(GROUP) == (2, 1, 2, GROUP)
    assert storage.get_LIST() == "%s 2 1 y" % GROUP
    assert storage.get_LISTGROUP(GROUP) == "1\r\n2"


def test_list_on_a_read_only_server(storage, monkeypatch):
    monkeypatch.setattr(settings, "server_type", "read-only")
    assert storage.get_LIST() == "%s 2 1 n" % GROUP


def test_article(storage):
    headers, body = storage.get_ARTICLE(GROUP, "1")
    assert headers.split("\r\n")[:2] == ["From: =?iso-8859-1?q?Jo=E3o?= <jpm@example.com>", "Subject: Olá mundo"]
    assert body == "first body\n.leading dot\n"


def test_8bit_headers_are_kept_intact(storage):
    # regression: mailbox's bytes parser turned these into =?unknown-8bit?...?=
    assert "Subject: Olá mundo" in storage.get_HEAD(GROUP, "1").split("\r\n")


def test_body_is_dot_stuffed(storage):
    assert storage.get_BODY(GROUP, "1") == "first body\n..leading dot\n"


def test_missing_articles(storage):
    assert storage.get_ARTICLE(GROUP, "3") is None
    assert storage.get_HEAD(GROUP, "3") is None
    assert storage.get_BODY(GROUP, "3") is None
    assert not storage.get_STAT(GROUP, "3")


@pytest.mark.parametrize("current, expected_next, expected_last", [
    ("1", 2, None), ("2", None, 1), ("3", None, None),
])
def test_next_and_last(storage, current, expected_next, expected_last):
    assert storage.get_NEXT(GROUP, current) == expected_next
    assert storage.get_LAST(GROUP, current) == expected_last


def test_xover(storage):
    lines = storage.get_XOVER(GROUP, "1").split("\r\n")
    assert [line.split("\t")[0] for line in lines] == ["1", "2"]
    fields = lines[1].split("\t")
    assert fields[1:6] == ["second", "Two <two@example.com>", "Tue, 2 Jan 2024 00:00:00 +0000",
                           "<2@example.com>", "<1@example.com>"]


def test_unsupported_commands(storage):
    assert storage.get_XPAT(GROUP, "Subject", "*", "1") is None
    assert storage.get_XHDR(GROUP, "Subject", "range", ("1",)) is None
    assert storage.get_XGTITLE() is None
    assert storage.do_POST(GROUP, "Subject: x\r\n\r\nbody", "127.0.0.1") is None
