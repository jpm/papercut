import os
import time

import pytest

import settings
from storage import maildir

GROUP = "papercut.maildir.test"


def write_article(group_dir, timestamp, n, subdir="cur", references=None):
    lines = [
        "From: Author %d <a%d@example.com>" % (n, n),
        "Subject: subject %d" % n,
        "Date: Mon, 1 Jan 2024 00:00:0%d +0000" % n,
    ]
    if references:
        lines.append("References: %s" % references)
    text = "\n".join(lines) + "\n\nbody %d\nsecond line\n" % n
    suffix = ":2," if subdir == "cur" else ""
    path = os.path.join(group_dir, subdir, "%d.M%dP1Q%d.host%s" % (timestamp, n, n, suffix))
    with open(path, "w") as f:
        f.write(text)
    return path


@pytest.fixture
def group_dir():
    path = os.path.join(settings.maildir_path, "test")
    for sub in ("new", "cur", "tmp"):
        os.makedirs(os.path.join(path, sub))
    # written out of order: articles are numbered by the timestamp in the name
    write_article(path, 1700000003, 3, references="<2@%s>" % GROUP)
    write_article(path, 1700000001, 1)
    write_article(path, 1700000002, 2)
    return path


@pytest.fixture
def storage(group_dir):
    return maildir.Papercut_Storage()


def test_groups_are_listed_with_the_prefix(storage):
    assert storage.get_groupname_list() == [GROUP]
    assert storage.group_exists(GROUP)
    assert storage.group_exists(GROUP.upper())
    assert not storage.group_exists("papercut.maildir.other")


def test_group_stats_count_the_articles(storage):
    # regression: the count used to be the number of entries in the group
    # directory (new, cur, tmp), so every group had 3 articles
    assert storage.get_GROUP(GROUP) == (3, 1, 3)
    assert storage.get_group_stats(GROUP) == (3, 1, 3, GROUP)
    assert storage.get_LISTGROUP(GROUP) == "1\r\n2\r\n3"


def test_counts_follow_new_articles(storage, group_dir):
    write_article(group_dir, 1700000004, 4)
    write_article(group_dir, 1700000005, 5)
    assert storage.get_GROUP(GROUP) == (5, 1, 5)
    assert storage.get_STAT(GROUP, "5")


def test_new_articles_are_moved_to_cur(storage, group_dir):
    write_article(group_dir, 1700000004, 4, subdir="new")
    assert storage.get_GROUP(GROUP) == (4, 1, 4)
    assert os.listdir(os.path.join(group_dir, "new")) == []
    assert "1700000004.M4P1Q4.host:2," in os.listdir(os.path.join(group_dir, "cur"))


def test_articles_are_numbered_by_timestamp(storage):
    assert storage.get_HEAD(GROUP, "1").count("subject 1") == 1
    assert "Subject: subject 3" in storage.get_HEAD(GROUP, "3")


def test_stat(storage):
    assert storage.get_STAT(GROUP, "3")
    assert not storage.get_STAT(GROUP, "4")


def test_message_ids_use_the_article_number(storage):
    # regression: message-ids were built from file names, which the server
    # cannot map back to an article number
    assert storage.get_message_id("2", GROUP) == "<2@%s>" % GROUP


def test_article(storage):
    headers, body = storage.get_ARTICLE(GROUP, "1")
    assert headers.split("\r\n") == [
        "From: Author 1 <a1@example.com>", "Subject: subject 1", "Date: Mon, 1 Jan 2024 00:00:01 +0000"]
    assert body == "body 1\nsecond line\n"


def test_article_that_does_not_exist(storage):
    assert storage.get_ARTICLE(GROUP, "9") is None
    assert storage.get_BODY(GROUP, "9") is None


def test_body_is_dot_stuffed(storage, group_dir):
    path = write_article(group_dir, 1700000004, 4)
    with open(path, "a") as f:
        f.write(".leading dot\n")
    assert storage.get_BODY(GROUP, "4").endswith("\n..leading dot\n")


def test_head(storage):
    head = storage.get_HEAD(GROUP, "2").split("\r\n")
    assert "From: Author 2 <a2@example.com>" in head
    assert "Newsgroups: %s" % GROUP in head
    assert "Message-ID: <2@%s>" % GROUP in head


@pytest.mark.parametrize("current, expected_next, expected_last", [
    ("1", 2, None), ("2", 3, 1), ("3", None, 2),
])
def test_next_and_last(storage, current, expected_next, expected_last):
    # regression: these compared the client's (string) article number with
    # an int, which raises TypeError on Python 3
    assert storage.get_NEXT(GROUP, current) == expected_next
    assert storage.get_LAST(GROUP, current) == expected_last


def test_xover(storage):
    lines = storage.get_XOVER(GROUP, "2").split("\r\n")
    assert len(lines) == 2
    fields = lines[1].split("\t")
    assert fields[:6] == ["3", "subject 3", "Author 3 <a3@example.com>",
                          "Mon, 1 Jan 2024 00:00:03 +0000", "<3@%s>" % GROUP, "<2@%s>" % GROUP]


def test_xover_range(storage):
    assert [l.split("\t")[0] for l in storage.get_XOVER(GROUP, "1", "2").split("\r\n")] == ["1", "2"]


@pytest.mark.parametrize("header, pattern, expected", [
    ("Subject", "*2", ["2 subject 2"]),
    ("From", "Author 3*", ["3 Author 3 <a3@example.com>"]),
    ("Message-ID", "<1@*", ["1 <1@%s>" % GROUP]),
    ("Subject", "nothing*", []),
])
def test_xpat(storage, header, pattern, expected):
    result = storage.get_XPAT(GROUP, header, pattern, "1")
    assert (result.split("\r\n") if result else []) == expected


def test_xhdr(storage):
    assert storage.get_XHDR(GROUP, "subject", "range", ("1", "2")) == "1 subject 1\r\n2 subject 2"
    assert storage.get_XHDR(GROUP, "message-id", "unique", ("3",)) == "3 <3@%s>" % GROUP
    assert storage.get_XHDR(GROUP, "lines", "range", ("1",)).split("\r\n")[0] == "1 2"


def test_newnews_returns_articles_newer_than_the_timestamp(storage, group_dir):
    old = os.path.join(group_dir, "cur", "1700000001.M1P1Q1.host:2,")
    os.utime(old, (1_000_000, 1_000_000))
    since = time.localtime(2_000_000)
    assert storage.get_NEWNEWS(since, GROUP).split("\r\n") == ["<2@%s>" % GROUP, "<3@%s>" % GROUP]
    assert storage.get_NEWNEWS(since, "*").split("\r\n") == ["<2@%s>" % GROUP, "<3@%s>" % GROUP]
    assert storage.get_NEWNEWS(time.localtime(time.time() + 60), GROUP) == ""


def test_post_writes_to_tmp_then_moves_to_new(storage, group_dir):
    assert storage.do_POST(GROUP, "Subject: posted\r\n\r\nbody ✓", "127.0.0.1") == 1
    assert os.listdir(os.path.join(group_dir, "tmp")) == []
    (name,) = os.listdir(os.path.join(group_dir, "new"))
    with open(os.path.join(group_dir, "new", name), encoding="utf-8", newline="") as f:
        assert f.read() == "Subject: posted\n\nbody ✓"
    assert storage.get_GROUP(GROUP) == (4, 1, 4)


def test_posted_articles_read_back_with_headers_and_body(storage):
    storage.do_POST(GROUP, "From: P <p@example.com>\r\nSubject: posted\r\n\r\nline 1\r\nline 2", "127.0.0.1")
    assert storage.get_BODY(GROUP, "4") == "line 1\nline 2"
    assert "Subject: posted" in storage.get_HEAD(GROUP, "4")
