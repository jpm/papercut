#!/usr/bin/env python
import nntplib
import re
import time
import StringIO

# We need setting.forward_host, which is the nntp server we forward to
import settings

# This is an additional backend for Papercut, currently it's more or less proof-of-concept.
# It's a "forwarding proxy", that merely forwards all requests to a "real" NNTP server.
# Just for fun, the post command adds an additional header.
#
# Written by Gerhard Häring (gerhard@bigfoot.de)

def log(s):
    # For debugging, replace with "pass" if this gets stable one day
    print s

class Papercut_Storage:
    def __init__(self):
        self.nntp = nntplib.NNTP(settings.forward_host)  

    def group_exists(self, group_name):
        try:
            self.nntp.group(group_name)
        except nntplib.NNTPTemporaryError, reason:
            return 0
        return 1

    def get_first_article(self, group_name):
        log(">get_first_article")
        # Not implemented
        return 1

    def get_group_stats(self, container):
        # log(">get_group_stats")
        # Returns: (total, maximum, minimum)
        max, min = container
        return (max-min, max, min)

    def get_message_id(self, msg_num, group):
        return '<%s@%s>' % (msg_num, group)

    def get_NEWGROUPS(self, ts, group='%'):
        log(">get_NEWGROUPS")
        date = time.strftime("%y%m%d", ts)
        tim = time.strftime("%H%M%S", ts)
        response, groups = self.nntp.newgroups(date, tim)
        return "\r\n".join(["%s" % k for k in (1,2,3)])

    def get_NEWNEWS(self, ts, group='*'):
        log(">get_NEWNEWS")
        articles = []
        articles.append("<%s@%s>" % (id, group))
        if len(articles) == 0:
            return ''
        else:
            return "\r\n".join(articles)

    def get_GROUP(self, group_name):
        # Returns: (total, first_id, last_id)   
        log(">get_GROUP")
        response, count, first, last, name = self.nntp.group(group_name)
        return (count, first, last)

    def get_LIST(self):
        # Returns: list of (groupname, table)
        log(">get_LIST")
        response, lst= self.nntp.list()
        def convert(x):
            return x[0], (int(x[1]), int(x[2]))
        lst = map(convert, lst)
        return lst

    def get_STAT(self, group_name, id):
        log(">get_STAT")
        try:
            resp, nr, id = self.nntp.stat(id)
            return nr
        except nntplib.NNTPTemporaryError, reason:
            return None

    def get_ARTICLE(self, group_name, id):
        log(">get_ARTICLE")
        resp, nr, id, headerlines = self.nntp.head(id)
        resp, nr, id, articlelines = self.nntp.article(id)
        dobreak = 0
        while 1:
            if articlelines[0] == "":
                dobreak = 1
            del articlelines[0]
            if dobreak:
                break
        return ("\r\n".join(headerlines), "\n".join(articlelines))

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
        resp, nr, mid, headerlines = self.nntp.head(id)
        return "\r\n".join(headerlines)

    def get_BODY(self, group_name, id):
        log(">get_BODY")
        resp, nr, mid, bodylines = self.nntp.body(id)
        return "\r\n".join(bodylines)

    def get_XOVER(self, group_name, start_id, end_id='ggg'):
        # subject\tauthor\tdate\tmessage-id\treferences\tbyte count\tline count\r\n
        log(">get_XOVER")
        xov = list(self.nntp.xover(start_id, end_id)[1])
        nxov = []
        for entry in xov:
            entry = list(entry)
            entry[5] = "\n".join(entry[5])
            nxov.append("\t".join(entry))
        return "\r\n".join(nxov)

    def get_LIST_ACTIVE(self, pat):
        log(">get_LIST_ACTIVE")
        resp, list = self.nntp.longcmd('LIST ACTIVE %s' % pat)
        return list

    def get_XPAT(self, group_name, header, pattern, start_id, end_id='ggg'):
        log(">get_XPAT")
        return None

    def get_LISTGROUP(self, group_name=""):
        log(">get_LISTGROUP")
        ids = []
        self.nntp.putcmd("LISTGROUP %s" % group_name)
        while 1:
            curline = self.nntp.getline()
            if curline == ".":
                break
            ids.append(curline)
        return "\r\n".join(ids)

    def get_XGTITLE(self, pattern="*"):
        log(">get_XGTITLE")
        resp, result = self.nntp.xgtitle(pattern)
        return "\r\n".join(["%s %s" % (group, title) for group, title in result])

    def get_XHDR(self, group_name, header, style, range):
        log(">get_XHDR")
        if style == "range":
            range = "-".join(range)
        resp, result = self.nntp.xhdr(header, range) 
        result = map(lambda x: x[1], result)
        return "\r\n".join(result)

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
        f = StringIO.StringIO(lines)
        result = self.nntp.post(f)
        return result