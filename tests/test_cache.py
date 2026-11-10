import os
import types

import pytest

import papercut_cache
import settings


class FakeStorage:
    """Backend that counts how often each method really runs."""
    calls = None

    def __init__(self):
        FakeStorage.calls = []

    def get_BODY(self, group, article):
        FakeStorage.calls.append(("get_BODY", group, article))
        return "body of %s/%s (call %d)" % (group, article, len(FakeStorage.calls))

    def get_XOVER(self, group, start, end="ggg"):
        FakeStorage.calls.append(("get_XOVER", group, start, end))
        return "overview %s-%s" % (start, end)

    def group_exists(self, group):
        FakeStorage.calls.append(("group_exists", group))
        return True

    some_attribute = "not callable"


@pytest.fixture
def cache():
    module = types.SimpleNamespace(Papercut_Storage=FakeStorage)
    return papercut_cache.Cache(module, papercut_cache.cache_methods)


@pytest.fixture
def clock(monkeypatch):
    """Controllable time.time() for the cache module."""
    now = [1_000_000.0]
    monkeypatch.setattr(papercut_cache.time, "time", lambda: now[0])
    return now


def test_second_identical_call_is_served_from_the_cache(cache):
    first = cache.get_BODY("g", "1")
    second = cache.get_BODY("g", "1")
    assert first == second == "body of g/1 (call 1)"
    assert len(FakeStorage.calls) == 1


def test_different_arguments_are_cached_separately(cache):
    cache.get_BODY("g", "1")
    cache.get_BODY("g", "2")
    cache.get_BODY("other", "1")
    cache.get_XOVER("g", "1", "5")
    cache.get_XOVER("g", "1")
    assert len(FakeStorage.calls) == 5


def test_methods_not_listed_as_cacheable_always_hit_the_backend(cache):
    assert "group_exists" not in papercut_cache.cache_methods
    cache.group_exists("g")
    cache.group_exists("g")
    assert len(FakeStorage.calls) == 2


def test_non_callable_attributes_pass_through(cache):
    assert cache.some_attribute == "not callable"


def test_entries_are_refreshed_after_they_expire(cache, clock, monkeypatch):
    monkeypatch.setattr(settings, "nntp_cache_expire", 60)
    cache.get_BODY("g", "1")
    clock[0] += 59
    assert cache.get_BODY("g", "1") == "body of g/1 (call 1)"
    clock[0] += 2  # now 61s after the entry was written
    assert cache.get_BODY("g", "1") == "body of g/1 (call 2)"
    assert len(FakeStorage.calls) == 2


def test_cache_files_are_written_to_the_cache_path_with_safe_names(cache):
    cache.get_BODY("../../etc", "<1@group>")
    files = os.listdir(settings.nntp_cache_path)
    assert len(files) == 1
    name = files[0]
    assert len(name) == 32 and all(c in "0123456789abcdef" for c in name)


def test_cache_file_names_are_stable(cache):
    wrapper = cache.get_BODY
    assert wrapper._get_filename("g", "1") == wrapper._get_filename("g", "1")
    assert wrapper._get_filename("g", "1") != wrapper._get_filename("g", "2")
