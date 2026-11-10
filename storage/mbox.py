#!/usr/bin/env python3
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: mbox.py,v 1.7 2004-08-01 01:51:48 jpm Exp $

import os
import email
import mailbox
import settings
from storage import strutil


def split_message(msg):
    """Returns (headers, body) for a mailbox message, as raw text."""
    text = msg.raw_text
    sep = text.find('\n\n')
    if sep == -1:
        return text, ''
    return text[:sep], text[sep + 2:]


class Papercut_Storage:
    """
    Storage backend interface for mbox files
    """
    mbox_dir = ''

    def __init__(self):
        self.mbox_dir = settings.mbox_path

    def get_messages(self, filename):
        """Returns the list of messages in the given mbox file."""
        mbox = mailbox.mbox(self.mbox_dir + filename, create=False)
        try:
            messages = []
            for key in mbox.keys():
                # parse from the raw text so 8-bit headers are kept as-is
                text = mbox.get_bytes(key).decode('utf-8', 'surrogateescape')
                msg = email.message_from_string(text)
                msg.raw_text = text
                messages.append(msg)
            return messages
        finally:
            mbox.close()

    def get_group_messages(self, group_name):
        return self.get_messages(group_name.replace('papercut.mbox.', ''))

    def get_file_list(self):
        return os.listdir(self.mbox_dir)

    def get_group_list(self):
        groups = self.get_file_list()
        return ["papercut.mbox.%s" % k for k in groups]

    def group_exists(self, group_name):
        # group names are supposed to be case insensitive
        group_name = group_name.lower()
        return any(name.lower() == group_name for name in self.get_group_list())

    def get_first_article(self, group_name):
        return 1

    def get_group_stats(self, group_name):
        total, max, min = self.get_mbox_stats(group_name.replace('papercut.mbox.', ''))
        return (total, min, max, group_name)

    def get_mbox_stats(self, filename):
        # the first message in the file is not served (see get_XOVER and
        # get_LISTGROUP), so the articles are 1 .. cnt-1
        cnt = len(self.get_messages(filename))
        return (cnt-1, cnt-1, 1)

    def get_message_id(self, msg_num, group):
        return '<%s@%s>' % (msg_num, group)

    def get_NEWGROUPS(self, ts, group='%'):
        # XXX: eventually add some code in here to get the mboxes newer than the given timestamp
        return None

    def get_NEWNEWS(self, ts, group='*'):
        return ''

    def get_GROUP(self, group_name):
        result = self.get_mbox_stats(group_name.replace('papercut.mbox.', ''))
        return (result[0], result[2], result[1])

    def get_LIST(self, username=""):
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
        return 0 <= int(id) < len(self.get_group_messages(group_name))

    def get_ARTICLE(self, group_name, id):
        msg = self.get_message(group_name, id)
        if msg is None:
            return None
        headers, body = split_message(msg)
        return ("\r\n".join(line.strip() for line in headers.split('\n')), body)

    def get_LAST(self, group_name, current_id):
        current_id = int(current_id)
        if current_id <= 1 or current_id >= len(self.get_group_messages(group_name)):
            return None
        return current_id - 1

    def get_NEXT(self, group_name, current_id):
        current_id = int(current_id)
        if current_id + 1 >= len(self.get_group_messages(group_name)):
            return None
        return current_id + 1

    def get_message(self, group_name, id):
        messages = self.get_group_messages(group_name)
        id = int(id)
        if 0 <= id < len(messages):
            return messages[id]
        return None

    def get_HEAD(self, group_name, id):
        msg = self.get_message(group_name, id)
        if msg is None:
            return None
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
            return strutil.format_body(split_message(msg)[1])

    def get_XOVER(self, group_name, start_id, end_id='ggg'):
        # don't count the first message
        messages = self.get_group_messages(group_name)[1:]
        overviews = []
        for i, msg in enumerate(messages, 1):
            body = split_message(msg)[1]
            author = msg.get('from')
            formatted_time = msg.get('date')
            message_id = msg.get('message-id')
            line_count = len(body.split('\n'))
            xref = 'Xref: %s %s:%s' % (settings.nntp_hostname, group_name, i)
            if msg.get('in-reply-to') is not None:
                reference = msg.get('in-reply-to')
            else:
                reference = ""
            # message_number <tab> subject <tab> author <tab> date <tab> message_id <tab> reference <tab> bytes <tab> lines <tab> xref
            overviews.append("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (i, msg.get('subject'), author, formatted_time, message_id, reference, len(strutil.format_body(body)), line_count, xref))
        return "\r\n".join(overviews)

    def get_XPAT(self, group_name, header, pattern, start_id, end_id='ggg'):
        # no support for this right now
        return None

    def get_LISTGROUP(self, group_name):
        # don't count the first message
        count = len(self.get_group_messages(group_name)) - 1
        return "\r\n".join(str(i) for i in range(1, count + 1))

    def get_XGTITLE(self, pattern=None):
        # no support for this right now
        return None

    def get_XHDR(self, group_name, header, style, range):
        # no support for this right now
        return None

    def do_POST(self, group_name, lines, ip_address, username=''):
        # let's make the mbox storage always read-only for now
        return None
