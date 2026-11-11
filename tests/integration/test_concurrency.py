"""Several clients at once, against the server as startup builds it.

Each client connection must get its own database connection: sharing one
between forked children (POSIX) or threads (Windows) interleaves their
queries and results.
"""
import multiprocessing
import os
import threading
import time
import warnings

import pytest

import serve
from conftest import settings_for

GROUP = "phorum.test"
CLIENTS = 6
ROUNDS = 15
TIMEOUT = 15      # per socket operation: a hang counts as a failure
DEADLINE = 90     # for the whole test

BACKENDS = {
    "phorum_mysql": ("mysql", "phorum"),
    "phorum_pgsql": ("postgres", "phorum"),
}


@pytest.fixture(params=["forking", "threading"])
def server_port(request, tmp_path):
    mode = request.param
    storage = request.node.callspec.params["backend"]
    kind, database = BACKENDS[storage]
    values = settings_for(kind, database, storage_backend=storage, nntp_cache="no", nntp_auth="no")
    context = multiprocessing.get_context("spawn")
    ports = context.Queue()
    process = context.Process(target=serve.run, args=(values, mode, str(tmp_path / "server.log"), ports), daemon=True)
    process.start()
    port = ports.get(timeout=30)
    yield port, tmp_path / "server.log"
    process.terminate()
    process.join(10)


def client_session(port, errors):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import nntplib
    try:
        with nntplib.NNTP("127.0.0.1", port, timeout=TIMEOUT) as s:
            for _ in range(ROUNDS):
                _, count, first, last, _ = s.group(GROUP)
                assert (count, first, last) == (3, 1, 4), (count, first, last)
                _, overviews = s.over((1, 4))
                assert [n for n, _ in overviews] == [1, 2, 4], overviews
                _, info = s.article("2")
                assert b"Subject: Re: First post" in info.lines, info.lines[:4]
                _, body = s.body("4")
                assert body.lines == ["Corpo com acentuação".encode()], body.lines
    except Exception as e:  # collected, so every client's failure is reported
        errors.append("%s: %s" % (type(e).__name__, e))


@pytest.mark.parametrize("backend", sorted(BACKENDS))
def test_concurrent_clients_get_correct_results(backend, server_port):
    port, log = server_port
    errors = []
    clients = [threading.Thread(target=client_session, args=(port, errors), daemon=True) for _ in range(CLIENTS)]
    for c in clients:
        c.start()
    deadline = time.time() + DEADLINE
    for c in clients:
        c.join(max(0, deadline - time.time()))
    hung = sum(c.is_alive() for c in clients)
    exceptions = sorted({l for l in log.read_text().splitlines() if l and not l.startswith((" ", "[", "Traceback"))}) if log.exists() else []
    server_errors = exceptions[:6]
    assert not hung and not errors, "%d of %d clients failed, %d hung; e.g.:\n%s\nserver log:\n%s" % (
        len(errors), CLIENTS, hung, "\n".join(errors[:3]), "\n".join(server_errors))
    # and the work really went through the server
    text = log.read_text()
    assert text.count("Connection from") == CLIENTS
    assert text.count("Received request: GROUP") == CLIENTS * ROUNDS
