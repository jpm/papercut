#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: mbox.py,v 1.5 2004-02-01 05:23:13 jpm Exp $

import os
import mailbox
import settings
import strutil
import string


class Papercut_Storage:
    """
    Storage backend interface for mbox files
    """
    mbox_dir = ''

    def __init__(self):
        self.mbox_dir = settings.mbox_path

    def get_mailbox(self, filename):
        return mailbox.PortableUnixMailbox(open(self.mbox_dir + filename))

    def get_file_list(self):
        return os.listdir(self.mbox_dir)

    def get_group_list(self):
        groups = self.get_file_list()
        return ["papercut.mbox.%s" % k for k in groups]

    def group_exists(self, group_name):
        groups = self.get_group_list()
        found = False
        for name in groups:
            # group names are supposed to be case insensitive
            if string.lower(name) == string.lower(group_name):
                found = True
                break
        return found

    def get_first_article(self, group_name):
        return 1

    def get_group_stats(self, filename):
        total, max, min = self.get_mbox_stats(filename)
        return (total, min, max, filename)

    def get_mbox_stats(self, filename):
        mbox = self.get_mailbox(filename)
        dir(mbox)
        cnt = 0
        while mbox.next():
            cnt = cnt + 1
        return (cnt-1, cnt, 1)

    def get_message_id(self, msg_num, group):
        return '<%s@%s>' % (msg_num, group)

    def get_NEWGROUPS(self, ts, group='%'):
        result = self.get_group_list()
        if len(result) == 0:
            return None
        else:
            return "\r\n".join(["%s" % k for k in result])

    def get_NEWNEWS(self, ts, group='*'):
        return ''

    def get_GROUP(self, group_name):
        result = self.get_mbox_stats(group_name.replace('papercut.mbox.', ''))
        return (result[0], result[2], result[1])

    def get_LIST(self):
        result = self.get_file_list()
        if len(result) == 0:
            return ""
        else:
            groups = []
            for mbox in result:
                total, maximum, minimum = self.get_mbox_stats(mbox)
                if settings.server_type == 'read-only':
                    groups.append("papercut.mbox.%s %s %s n" % (mbox, maximum, minimum))
                else:
                    groups.append("papercut.mbox.%s %s %s y" % (mbox, maximum, minimum))
            return "\r\n".join(groups)

    def get_STAT(self, group_name, id):
        # check if the message exists
        mbox = self.get_mailbox(group_name.replace('papercut.mbox.', ''))
        i = 0
        while mbox.next():
            if i == int(id):
                return True
            i = i + 1
        return False

    def get_ARTICLE(self, group_name, id):
        mbox = self.get_mailbox(group_name.replace('papercut.mbox.', ''))
        i = 0
        while 1:
            msg = mbox.next()
            if msg is None:
                return None
            if i == int(id):
                return ("\r\n".join(["%s" % string.strip(k) for k in msg.headers]), msg.fp.read())
            i = i + 1

    def get_LAST(self, group_name, current_id):
        mbox = self.get_mailbox(group_name.replace('papercut.mbox.', ''))
        if current_id == 1:
            return None
        else:
            i = 0
            while 1:
                msg = mbox.next()
                if msg is None:
                    return None
                if (i+1) == current_id:
                    return i
                i = i + 1

    def get_NEXT(self, group_name, current_id):
        mbox = self.get_mailbox(group_name.replace('papercut.mbox.', ''))
        print repr(current_id)
        i = 0
        while 1:
            msg = mbox.next()
            if msg is None:
                return None
            if i > current_id:
                return i
            i = i + 1

    def get_message(self, group_name, id):
        mbox = self.get_mailbox(group_name.replace('papercut.mbox.', ''))
        i = 0
        while 1:
            msg = mbox.next()
            if msg is None:
                return None
            if i == int(id):
                return msg
            i = i + 1

    def get_HEAD(self, group_name, id):
        msg = self.get_message(group_name, id)
        headers = []
        headers.append("Path: %s" % (settings.nntp_hostname))
        headers.append("From: %s" % (msg.get('from')))
        headers.append("Newsgroups: %s" % (group_name))
        headers.append("Date: %s" % (msg.get('date')))
        headers.append("Subject: %s" % (msg.get('subject')))
        headers.append("Message-ID: <%s@%s>" % (id, group_name))
        headers.append("Xref: %s %s:%s" % (settings.nntp_hostname, group_name, id))
        return "\r\n".join(headers)

    def get_BODY(self, group_name, id):
        msg = self.get_message(group_name, id)
        if msg is None:
            return None
        else:
            return strutil.format_body(msg.fp.read())

    def get_XOVER(self, group_name, start_id, end_id='ggg'):
        mbox = self.get_mailbox(group_name.replace('papercut.mbox.', ''))
        # don't count the first message
        mbox.next()
        i = 1
        overviews = []
        while 1:
            msg = mbox.next()
            if msg is None:
                break
            author = msg.get('from')
            formatted_time = msg.get('date')
            message_id = msg.get('message-id')
            line_count = len(msg.fp.read().split('\n'))
            xref = 'Xref: %s %s:%s' % (settings.nntp_hostname, group_name, i)
            if msg.get('in-reply-to') is not None:
                reference = msg.get('in-reply-to')
            else:
                reference = ""
            # message_number <tab> subject <tab> author <tab> date <tab> message_id <tab> reference <tab> bytes <tab> lines <tab> xref
            overviews.append("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (i, msg.get('subject'), author, formatted_time, message_id, reference, len(strutil.format_body(msg.fp.read())), line_count, xref))
            i = i + 1
        return "\r\n".join(overviews)

    def get_XPAT(self, group_name, header, pattern, start_id, end_id='ggg'):
        # no support for this right now
        return None

    def get_LISTGROUP(self, group_name):
        mbox = self.get_mailbox(group_name.replace('papercut.mbox.', ''))
        # don't count the first message
        mbox.next()
        i = 0
        ids = []
        while 1:
            msg = mbox.next()
            if msg is None:
                break
            i = i + 1
            ids.append(i)
        return "\r\n".join(ids)

    def get_XGTITLE(self, pattern=None):
        # no support for this right now
        return None

    def get_XHDR(self, group_name, header, style, range):
        # no support for this right now
        return None

    def do_POST(self, group_name, lines, ip_address, username=''):
        # let's make the mbox storage always read-only for now
        return None
