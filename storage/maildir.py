#!/usr/bin/env python
# Copyright (c) 2004 Scott Parish, Joao Prado Maia
# See the LICENSE file for more information.
# $Id: maildir.py,v 1.2 2004-08-01 01:51:48 jpm Exp $

#
# Maildir backend for papercut
#
# Notes:
#
# Currently the numeric message ids are based off the number of
# files in that group's directy. This means that if you change
# a file name, or delete a file you are going to change ids, which
# in turn is going to confuse nntp clients!
#
# To add a new group:
#     mkdir -p /home/papercut/maildir/my.new.group/{new,cur,tmp}
#

import dircache
from fnmatch import fnmatch
import glob
import os
import mailbox
import rfc822
import settings
import socket
import strutil
import string
import time


def maildir_date_cmp(a, b):
    """compare maildir file names 'a' and 'b' for sort()"""
    a = os.path.basename(a)
    b = os.path.basename(b)
    a = int(a[: a.find(".")])
    b = int(b[: b.find(".")])
    return cmp(a, b)



class Papercut_Storage:
    """
    Storage backend interface for mbox files
    """
    _proc_post_count = 0

    def __init__(self, group_prefix="papercut.maildir."):
        self.maildir_dir = settings.maildir_path
        self.group_prefix = group_prefix


    def _get_group_dir(self, group):
        return os.path.join(self.maildir_dir, group)


    def _groupname2group(self, group_name):
        return group_name.replace(self.group_prefix, '')


    def _group2groupname(self, group):
        return self.group_prefix + group


    def _new_to_cur(self, group):
        groupdir = self._get_group_dir(group)
        for f in dircache.listdir(os.path.join(groupdir, 'new')):
            ofp = os.path.join(groupdir, 'new', f)
            nfp = os.path.join(groupdir, 'cur', f + ":2,")
            os.rename(ofp, nfp)


    def get_groupname_list(self):
        groups = dircache.listdir(self.maildir_dir)
        return ["papercut.maildir.%s" % k for k in groups]


    def get_group_article_list(self, group):
        self._new_to_cur(group)
        groupdir = self._get_group_dir(group)
        articledir = os.path.join(self._get_group_dir(group), 'cur')
        articles = dircache.listdir(articledir)
        articles.sort(maildir_date_cmp)
        return articles

    
    def get_group_article_count(self, group):
        self._new_to_cur(group)
        articles = dircache.listdir(os.path.join(self.maildir_dir, group))
        return len(articles)

       
    def group_exists(self, group_name):
        groupnames = self.get_groupname_list()
        found = False
        
        for name in groupnames:
            # group names are supposed to be case insensitive
            if string.lower(name) == string.lower(group_name):
                found = True
                break
            
        return found


    def get_first_article(self, group_name):
        return 1


    def get_group_stats(self, group_name):
        total, max, min = self.get_maildir_stats(group_name)
        return (total, min, max, group_name)


    def get_maildir_stats(self, group_name):
        cnt = len(self.get_group_article_list(group_name))
        return cnt, cnt, 1


    def get_message_id(self, msg_num, group_name):
        msg_num = int(msg_num)
        group = self._groupname2group(group_name)
        return '<%s@%s>' % (self.get_group_article_list(group)[msg_num - 1],
                            group_name)


    def get_NEWGROUPS(self, ts, group='%'):
        return None


    # UNTESTED
    def get_NEWNEWS(self, ts, group='*'):
        gpaths = glob.glob(os.path.join(self.maildir_dir, group))
        articles = []
        for gpath in gpaths:
            articles = dircache.listdir(os.path.join(gpath, "cur"))
            group = os.path.basename(gpath)
            group_name = self._group2groupname(group)

            for article in articles:
                apath = os.path.join(gpath, "cur", article)
                if os.path.getmtime(apath) < ts:
                    continue

                articles.append("<%s@%s" % (article, group_name))

        if len(articles) == 0:
            return ''
        else:
            return "\r\n".join(articles)


    def get_GROUP(self, group_name):
        group = self._groupname2group(group_name)
        result = self.get_maildir_stats(group)
        return (result[0], result[2], result[1])


    def get_LIST(self, username=""):
        result = self.get_groupname_list()
        
        if len(result) == 0:
            return ""
        
        else:
            groups = []
            mutable = ('y', 'n')[settings.server_type == 'read-only']
            
            for group_name in result:
                group = self._groupname2group(group_name)
                total, maximum, minimum = self.get_maildir_stats(group)
                groups.append("%s %s %s %s" % (group_name, maximum,
                                               minimum, mutable))
            return "\r\n".join(groups)


    def get_STAT(self, group_name, id):
        # check if the message exists
        id = int(id)
        group = self._groupname2group(group_name)
        
        return id <= self.get_group_article_count(group)

        
    def get_message(self, group_name, id):
        group = self._groupname2group(group_name)
        id = int(id)
        
        try:
            article = self.get_group_article_list(group)[id - 1]
            file = os.path.join(self.maildir_dir, group, "cur", article)
            return rfc822.Message(open(file))
        
        except IndexError:
            return None


    def get_ARTICLE(self, group_name, id):
        msg = self.get_message(group_name, id)
        if not msg:
            return None
        return ("\r\n".join(["%s" % string.strip(k) for k in msg.headers]), msg.fp.read())


    def get_LAST(self, group_name, current_id):
        if current_id <= 1:
            return None
        return current_id - 1


    def get_NEXT(self, group_name, current_id):
        group = self._groupname2group(group_name)
        if current_id >= self.get_group_article_count(group):
            return None
        return current_id + 1
        

    def get_HEAD(self, group_name, id):
        msg = self.get_message(group_name, id)
        headers = []
        headers.append("Path: %s" % (settings.nntp_hostname))
        headers.append("From: %s" % (msg.get('from')))
        headers.append("Newsgroups: %s" % (group_name))
        headers.append("Date: %s" % (msg.get('date')))
        headers.append("Subject: %s" % (msg.get('subject')))
        headers.append("Message-ID: <%s@%s>" % (id, group_name))
        headers.append("Xref: %s %s:%s" % (settings.nntp_hostname,
                                           group_name, id))
        return "\r\n".join(headers)


    def get_BODY(self, group_name, id):
        msg = self.get_message(group_name, id)
        if msg is None:
            return None
        else:
            return strutil.format_body(msg.fp.read())


    def get_XOVER(self, group_name, start_id, end_id='ggg'):
        group = self._groupname2group(group_name)
        start_id = int(start_id)
        if end_id == 'ggg':
            end_id = self.get_group_article_count(group)
        else:
            end_id = int(end_id)
            
        overviews = []
        for id in range(start_id, end_id + 1):
            msg = self.get_message(group_name, id)
            
            if msg is None:
                break
            
            author = msg.get('from')
            formatted_time = msg.get('date')
            message_id = self.get_message_id(id, group_name)
            line_count = len(msg.fp.read().split('\n'))
            xref = 'Xref: %s %s:%d' % (settings.nntp_hostname, group_name, id)
            
            if msg.get('references') is not None:
                reference = msg.get('references')
            else:
                reference = ""
            # message_number <tab> subject <tab> author <tab> date <tab>
            # message_id <tab> reference <tab> bytes <tab> lines <tab> xref
            
            overviews.append("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % \
                             (id, msg.get('subject'), author,
                              formatted_time, message_id, reference,
                              len(strutil.format_body(msg.fp.read())),
                              line_count, xref))
            
        return "\r\n".join(overviews)


    # UNTESTED
    def get_XPAT(self, group_name, header, pattern, start_id, end_id='ggg'):
        group = self._groupname2group(group_name)
        header = header.upper()
        start_id = int(start_id)
        if end_id == 'ggg':
            end_id = self.get_group_article_count(group)
        else:
            end_id = int(end_id)

        hdrs = []
        for id in range(start_id, end_id + 1):

            if header == 'MESSAGE-ID':
                msg_id = self.get_message_id(id, group_name)
                if fnmatch(msg_id, pattern):
                    hdrs.append('%d %s' % (id, msg_id))
                continue
            elif header == 'XREF':
                xref = '%s %s:%d' % (settings.nntp_hostname, group_name, id)
                if fnmatch(xref, pattern):
                    hdrs.append('%d %s' % (id, xref))
                continue
            
            msg = self.get_message(group_name, id)
            if header == 'BYTES':
                msg.fp.seek(0, 2)
                bytes = msg.fp.tell()
                if fnmatch(str(bytes), pattern):
                    hdrs.append('%d %d' % (id, bytes))
            elif header == 'LINES':
                lines = len(msg.fp.readlines())
                if fnmatch(str(lines), pattern):
                    hdrs.append('%d %d' % (id, lines))
            else:
                hdr = msg.get(header)
                if hdr and fnmatch(hdr, pattern):
                    hdrs.append('%d %s' % (id, hdr))

        if len(hdrs):
            return "\r\n".join(hdrs)
        else:
            return ""


    def get_LISTGROUP(self, group_name):
        ids = range(1, self.get_group_article_count(group) + 1)
        ids = [str(id) for id in ids]
        return "\r\n".join(ids)

    def get_XGTITLE(self, pattern=None):
        # XXX no support for this right now
        return ''


    def get_XHDR(self, group_name, header, style, ranges):
        print group_name, header, style, ranges
        group = self._groupname2group(group_name)
        header = header.upper()

        if style == 'range':
            if len(ranges) == 2:
                range_end = int(ranges[1])
            else:
                range_end = self.get_group_article_count(group)
            ids = range(int(ranges[0]), range_end + 1)
        else:
            ids = (int(ranges[0]))

        hdrs = []
        for id in ids:
            if header == 'MESSAGE-ID':
                hdrs.append('%d %s' % \
                            (id, self.get_message_id(id, group_name)))
                continue
            elif header == 'XREF':
                hdrs.append('%d %s %s:%d' % (id, settings.nntp_hostname,
                                             group_name, id))
                continue

            msg = self.get_message(group_name, id)
            if header == 'BYTES':
                msg.fp.seek(0, 2)
                hdrs.append('%d %d' % (id, msg.fp.tell()))
            elif header == 'LINES':
                hdrs.append('%d %d' % (id, len(msg.fp.readlines())))
            else:
                hdr = msg.get(header)
                if hdr:
                    hdrs.append('%d %s' % (id, hdr))

        if len(hdrs) == 0:
            return ""
        else:
            return "\r\n".join(hdrs)


    def do_POST(self, group_name, body, ip_address, username=''):
        self._proc_post_count += 1
        count = self._proc_post_count

        ts = [int(x) for x in str(time.time()).split(".")]
        file = "%d.M%dP%dQ%d.%s" % (ts[0], ts[1], os.getpid(),
                                    count, socket.gethostname())
        group = self._groupname2group(group_name)
        groupdir = self._get_group_dir(group)
        tfpath = os.path.join(self.maildir_dir, groupdir, "tmp", file)
        nfpath = os.path.join(self.maildir_dir, groupdir, "new", file)
        
        fd = open(tfpath, 'w')
        fd.write(body)
        fd.close

        os.rename(tfpath, nfpath)
        return 1

