import threading
import time

import pytest

from storage import strutil


# --- mime_decode_header (replacement for the removed mimify module) ---

@pytest.mark.parametrize("encoded, expected", [
    ("=?iso-8859-1?q?Jo=E3o?=", "João"),
    ("=?ISO-8859-1?Q?Jo=E3o?=", "João"),
    ("=?utf-8?q?Ol=C3=A1?=", "Olá"),
    ("=?iso-8859-1?q?Jo=E3o_Maia?=", "João Maia"),
])
def test_mime_decode_header_decodes_q_encoded_words(encoded, expected):
    assert strutil.mime_decode_header(encoded) == expected


def test_mime_decode_header_decodes_every_word_and_keeps_the_rest():
    text = "From: =?iso-8859-1?q?Jo=E3o?= <jpm@example.com>\r\nSubject: =?utf-8?q?Ol=C3=A1?= mundo\r\n"
    assert strutil.mime_decode_header(text) == "From: João <jpm@example.com>\r\nSubject: Olá mundo\r\n"


def test_mime_decode_header_unknown_charset_falls_back_to_latin1():
    assert strutil.mime_decode_header("=?x-made-up?q?caf=E9?=") == "café"


def test_mime_decode_header_invalid_bytes_for_charset_fall_back_to_latin1():
    # 0xE9 alone is not valid UTF-8
    assert strutil.mime_decode_header("=?utf-8?q?caf=E9?=") == "café"


@pytest.mark.parametrize("text", [
    "Subject: plain ascii",
    "Subject: =?iso-8859-1?b?Sm/jbw==?=",  # base64 words are left alone
    "",
])
def test_mime_decode_header_leaves_other_text_unchanged(text):
    assert strutil.mime_decode_header(text) == text


# --- format_body (NNTP dot-stuffing) ---

def test_format_body_doubles_leading_dots():
    assert strutil.format_body(".start\nmiddle.dot\n..two\n.") == "..start\nmiddle.dot\n...two\n.."


def test_format_body_without_leading_dots_is_unchanged():
    assert strutil.format_body("no dots\nhere.") == "no dots\nhere."


# --- wrap ---

def run_with_deadline(func, *args, seconds=5):
    """Runs func in a thread so a regression to an infinite loop fails the
    test instead of hanging the whole suite."""
    result = []
    worker = threading.Thread(target=lambda: result.append(func(*args)), daemon=True)
    worker.start()
    worker.join(seconds)
    assert not worker.is_alive(), "%s did not finish within %ss" % (func.__name__, seconds)
    return result[0]


def test_wrap_breaks_lines_at_spaces_within_the_width():
    wrapped = strutil.wrap("word " * 30, width=20)
    lines = wrapped.split("\n")
    assert len(lines) > 1
    assert all(len(line) <= 20 for line in lines)
    assert wrapped.replace("\n", " ") == "word " * 30


def test_wrap_short_text_is_unchanged():
    assert strutil.wrap("short line", width=78) == "short line"


def test_wrap_keeps_existing_newlines():
    text = "first line\nsecond line"
    assert strutil.wrap(text, width=78) == text


def test_wrap_long_word_followed_by_text_breaks_after_the_word():
    assert strutil.wrap("a" * 30 + " tail", width=10) == "a" * 30 + "\ntail"


@pytest.mark.parametrize("text", [
    "x" * 100,
    "short\n" + "y" * 90,
    "a few words then " + "z" * 120,
], ids=["long-word", "newline-then-long-word", "words-then-long-word"])
def test_wrap_terminates_on_long_text_without_spaces(text):
    # regression: this used to loop forever (posting an article ending in a
    # long URL hung the Phorum backends' moderator notification)
    wrapped = run_with_deadline(strutil.wrap, text)
    assert wrapped.replace("\n", " ") == text.replace("\n", " ")


# --- get_formatted_time ---

def test_get_formatted_time_has_no_leading_zero_on_the_day():
    t = time.strptime("2024-01-05 09:08:07", "%Y-%m-%d %H:%M:%S")
    formatted = strutil.get_formatted_time(t)
    assert formatted.startswith("Fri, 5 Jan 2024 09:08:07")


# --- wildcards ---

def test_format_wildcards_converts_to_a_regexp():
    assert strutil.format_wildcards("comp.*.misc?") == "comp..*.misc.*"


def test_format_wildcards_sql_converts_to_like_syntax():
    assert strutil.format_wildcards_sql("comp.*.misc?") == "comp.%.misc%"
