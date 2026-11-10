"""Shared test setup.

settings.py points at /home/papercut/... by default; every test gets
temporary directories instead, so nothing is written outside tmp_path.
"""
import pytest

import settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    for name in ("logs", "cache", "mboxes", "maildir"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(settings, "log_file", str(tmp_path / "logs" / "papercut.log"))
    monkeypatch.setattr(settings, "nntp_cache_path", str(tmp_path / "cache") + "/")
    monkeypatch.setattr(settings, "mbox_path", str(tmp_path / "mboxes") + "/")
    monkeypatch.setattr(settings, "maildir_path", str(tmp_path / "maildir") + "/")
    return settings
