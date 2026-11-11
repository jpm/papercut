"""Runs a Papercut server in its own process (see test_concurrency.py).

Imported by multiprocessing's 'spawn' start method, so a server that
crashes (e.g. a DB driver misused from several threads) fails the test
instead of taking pytest down with it.
"""
import socketserver


class ThreadingServer(socketserver.ThreadingTCPServer):
    """The server class Papercut uses on Windows."""
    allow_reuse_address = True
    daemon_threads = True


def run(settings_values, mode, log_file, port_queue):
    import settings
    for name, value in settings_values.items():
        setattr(settings, name, value)
    settings.log_file = log_file
    import papercut
    server_class = ThreadingServer if mode == "threading" else papercut.NNTPServer
    server = papercut.build_server(("127.0.0.1", 0), server_class)
    port_queue.put(server.server_address[1])
    server.serve_forever()
