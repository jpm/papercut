"""Test doubles shared by the test modules."""
import socket
import socketserver
import threading


class FakeBackend:
    """Storage backend that records every call and returns canned data.

    Override a return value with `backend.returns["get_BODY"] = ...`; a value
    that is an exception instance is raised instead of returned.
    """

    DEFAULTS = {
        "group_exists": True,
        "get_GROUP": (3, 1, 3),
        "get_group_stats": (3, 1, 3, "test.group"),
        "get_first_article": 1,
        "get_message_id": "<1@test.group>",
        "get_STAT": True,
        "get_ARTICLE": ("Subject: hello\r\nFrom: someone", "body text"),
        "get_HEAD": "Subject: hello\r\nFrom: someone",
        "get_BODY": "body text",
        "get_NEXT": 2,
        "get_LAST": 1,
        "get_XOVER": "1\thello\tsomeone\tdate\t<1@test.group>\t\t9\t1\txref",
        "get_XPAT": "1 hello",
        "get_XHDR": "1 hello",
        "get_LIST": "test.group 3 1 y",
        "get_LISTGROUP": "1\r\n2\r\n3",
        "get_XGTITLE": "test.group A test group",
        "get_NEWGROUPS": None,
        "get_NEWNEWS": "",
        "do_POST": 1,
    }

    def __init__(self):
        self.calls = []
        self.returns = dict(self.DEFAULTS)

    def __getattr__(self, name):
        if name not in self.DEFAULTS:
            raise AttributeError(name)

        def method(*args):
            self.calls.append((name,) + args)
            value = self.returns[name]
            if isinstance(value, BaseException):
                raise value
            return value
        return method

    def called(self, name):
        """Arguments of every call to `name`."""
        return [call[1:] for call in self.calls if call[0] == name]


class FakeAuth:
    def __init__(self, users):
        self.users = users
        self.calls = []

    def is_valid_user(self, username, password):
        self.calls.append((username, password))
        return self.users.get(username) == password


class FakeServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    backend = None
    auth = None


def start_server(handler_class, backend, auth=None):
    server = FakeServer(("127.0.0.1", 0), handler_class)
    server.backend = backend
    server.auth = auth
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class Client:
    """Minimal line-oriented NNTP client that works with raw bytes."""

    def __init__(self, port, timeout=5):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.file = self.sock.makefile("rwb")
        self.greeting = self.readline()

    def send(self, line):
        if isinstance(line, str):
            line = line.encode("utf-8")
        self.file.write(line + b"\r\n")
        self.file.flush()

    def readline_bytes(self):
        return self.file.readline()

    def readline(self):
        return self.readline_bytes().decode("utf-8", "surrogateescape").rstrip("\r\n")

    def cmd(self, line):
        """Sends a command and returns the status line."""
        self.send(line)
        return self.readline()

    def read_multiline(self):
        """Reads the lines of a multi-line response, up to the final '.'."""
        lines = []
        while True:
            line = self.readline()
            if line == ".":
                return lines
            lines.append(line)

    def close(self):
        self.file.close()
        self.sock.close()
