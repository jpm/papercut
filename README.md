# Papercut NNTP Server

Papercut is a news server written in 100% pure Python. It is intended to be
extensible to the point where people can develop their own plug-ins and by
that integrate the NNTP protocol to their applications.

The server is compliant with most of the [RFC 977](docs/rfc0977.txt) standards
(when they make sense and are needed) and implements a lot of
[RFC 1036](docs/rfc1036.txt) and [RFC 2980](docs/rfc2980.txt) extensions to the
NNTP protocol. It was tested against Netscape News, Mozilla News and tin (under
Solaris) and it works properly.

> **Python versions:** Papercut now runs on Python 3. The original code, which
> targets Python 2.2, is preserved under the
> [`python-2.2`](https://github.com/jpm/papercut/tree/python-2.2) tag.

## Quick start

```sh
pip install -r requirements.txt   # only what your backend needs; see the file
$EDITOR settings.py               # paths, hostname/port, storage backend
python3 papercut.py
```

See [INSTALL](INSTALL) for step by step instructions.

## Running the tests

```sh
pip install -r requirements-dev.txt
pytest
```

See [docs/unit-testing-plan.md](docs/unit-testing-plan.md) and
[docs/integration-testing-plan.md](docs/integration-testing-plan.md) for what
is covered and what's planned.

## Storage backends

The original need for this server was to integrate my PHP related web site
forums with an NNTP gateway interface, so people could list and read the
messages posted to the forums on their favorite News reader. The software on
this case was [Phorum](http://phorum.org) and the site is
[PHPBrasil.com](http://phpbrasil.com). At first it wasn't intended to support
message posting, but it made sense to allow it after seeing how effective the
tool was.

The concept of storage modules was created exactly for this. I would create a
Python class to handle the inner-workings of Phorum and MySQL and if I ever
wanted to integrate the server with another type of software, I would just need
to write a new storage module class.

Available backends (set `storage_backend` in `settings.py`):

| Backend | Storage |
| --- | --- |
| `phorum_mysql`, `phorum_pgsql` | Phorum forums on MySQL / PostgreSQL |
| `phpbb_mysql`, `phpnuke_phpbb_mysql` | phpBB (standalone or PHP-Nuke) on MySQL |
| `mysql` | Papercut's own MySQL schema (`storage/mysql_storage.sql`) |
| `mbox` | mbox files (read-only) |
| `maildir` | Maildir directories |
| `forwarding_proxy` | Forwards requests to another NNTP server (proof of concept) |

## Performance

Papercut is multi-threaded on Windows platforms and forking-based on UNIX
platforms and should be reasonably fast (that means basically: it's pretty
fast, but don't try serving 1000 connections at a time). The best thing about
the application is that it is very simple to extend it.

## License

Papercut is licensed under the BSD license (see [LICENSE](LICENSE)), which
means you can sell it or do whatever you like with it. However, I ask that if
you think Papercut is a good tool and you made a few enhancements to it or even
fixed some bugs, please send me a patch or something. I will appreciate it :)

-- Joao Prado Maia (jpm@pessoal.org)
