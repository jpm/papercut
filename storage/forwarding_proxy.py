#!/usr/bin/env python3
import datetime
import io
import time

# nntplib was removed from the standard library in Python 3.13;
# on newer versions install the 'standard-nntplib' package
import nntplib

# We need setting.forward_host, which is the nntp server we forward to
import settings

# This is an additional backend for Papercut, currently it's more or less proof-of-concept.
# It's a "forwarding proxy", that merely forwards all requests to a "real" NNTP server.
# Just for fun, the post command adds an additional header.
#
# Written by Gerhard Häring (gerhard@bigfoot.de)

def log(s):
    # For debugging, replace with "pass" if this gets stable one day
    print(s)

def decode_lines(lines):
    # Python 3's nntplib returns raw bytes for article content
    return [l.decode('utf-8', 'surrogateescape') for l in lines]

class Papercut_Storage:
    def __init__(self):
        self.nntp = nntplib.NNTP(settings.forward_host)  

    def group_exists(self, group_name):
        try:
            self.nntp.group(group_name)
        except nntplib.NNTPTemporaryError:
            return 0
        return 1

    def get_first_article(self, group_name):
        log(">get_first_article")
        # Not implemented
        return 1

    def get_group_stats(self, group_name):
        # Returns: (total, first, last, group_name), like the other backends
        # (this used to unpack the group name as a (max, min) pair)
        response, count, first, last, name = self.nntp.group(group_name)
        return (count, first, last, group_name)

    def get_message_id(self, msg_num, group):
        return '<%s@%s>' % (msg_num, group)

    def get_NEWGROUPS(self, ts, group='%'):
        log(">get_NEWGROUPS")
        since = datetime.datetime.fromtimestamp(time.mktime(ts))
        response, groups = self.nntp.newgroups(since)
        return "\r\n".join(["%s %s %s %s" % tuple(g) for g in groups])

    def get_NEWNEWS(self, ts, group='*'):
        log(">get_NEWNEWS")
        since = datetime.datetime.fromtimestamp(time.mktime(ts))
        response, articles = self.nntp.newnews(group, since)
        if len(articles) == 0:
            return ''
        else:
            return "\r\n".join(articles)

    def get_GROUP(self, group_name):
        # Returns: (total, first_id, last_id)   
        log(">get_GROUP")
        response, count, first, last, name = self.nntp.group(group_name)
        return (count, first, last)

    def get_LIST(self, username=""):
        # Returns: list of (groupname, table)
        log(">get_LIST")
        response, lst = self.nntp.list()
        return "\r\n".join(["%s %s %s %s" % tuple(g) for g in lst])

    def get_STAT(self, group_name, id):
        log(">get_STAT")
        try:
            resp, nr, id = self.nntp.stat(id)
            return nr
        except nntplib.NNTPTemporaryError:
            return None

    def get_ARTICLE(self, group_name, id):
        log(">get_ARTICLE")
        resp, info = self.nntp.article(id)
        lines = decode_lines(info.lines)
        # headers end at the first empty line
        sep = lines.index("") if "" in lines else len(lines)
        return ("\r\n".join(lines[:sep]), "\r\n".join(lines[sep + 1:]))

    def get_LAST(self, group_name, current_id):
        log(">get_LAST")
        # Not implemented
        return None

    def get_NEXT(self, group_name, current_id):
        log(">get_NEXT")
        # Not implemented
        return None

    def get_HEAD(self, group_name, id):
        log(">get_HEAD")
        resp, info = self.nntp.head(id)
        return "\r\n".join(decode_lines(info.lines))

    def get_BODY(self, group_name, id):
        log(">get_BODY")
        resp, info = self.nntp.body(id)
        return "\r\n".join(decode_lines(info.lines))

    def get_XOVER(self, group_name, start_id, end_id='ggg'):
        # subject\tauthor\tdate\tmessage-id\treferences\tbyte count\tline count\r\n
        log(">get_XOVER")
        if end_id == 'ggg':
            end_id = None
        resp, xov = self.nntp.over((int(start_id), end_id and int(end_id)))
        fields = ('subject', 'from', 'date', 'message-id', 'references', ':bytes', ':lines', 'xref')
        nxov = []
        for number, overview in xov:
            nxov.append("\t".join([str(number)] + [overview.get(f) or '' for f in fields]))
        return "\r\n".join(nxov)

    def get_LIST_ACTIVE(self, pat):
        log(">get_LIST_ACTIVE")
        resp, groups = self.nntp.list(pat)
        return ["%s %s %s %s" % tuple(g) for g in groups]

    def get_XPAT(self, group_name, header, pattern, start_id, end_id='ggg'):
        log(">get_XPAT")
        return None

    def get_LISTGROUP(self, group_name=""):
        log(">get_LISTGROUP")
        resp, lines = self.nntp._longcmdstring("LISTGROUP %s" % group_name)
        return "\r\n".join(lines)

    def get_XGTITLE(self, pattern="*"):
        log(">get_XGTITLE")
        resp, result = self.nntp.descriptions(pattern)
        return "\r\n".join(["%s %s" % (group, title) for group, title in result.items()])

    def get_XHDR(self, group_name, header, style, range):
        log(">get_XHDR")
        if style == "range":
            if isinstance(range, str):
                # open-ended range: the server passes just the start
                # ("-".join("12") used to turn this into "1-2")
                range = range + "-"
            else:
                range = "-".join(range)
        resp, result = self.nntp.xhdr(header, range) 
        return "\r\n".join(["%s %s" % (num, text) for num, text in result])

    def do_POST(self, group_name, lines, ip_address, username=''):
        log(">do_POST")  
        while lines.find("\r") > 0:
            lines = lines.replace("\r", "")
        lns = lines.split("\n")
        counter = 0
        for l in lns:
            if l == "":
                lns.insert(counter, "X-Modified-By: Papercut's forwarding backend")
                break
            counter +=1
        lines = "\n".join(lns)
        # we need to send an actual file
        f = io.BytesIO(lines.encode('utf-8', 'surrogateescape'))
        result = self.nntp.post(f)
        return result