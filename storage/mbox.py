#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: mbox.py,v 1.1 2002-12-13 07:32:10 jpm Exp $

import os
import mailbox
import settings


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
        if group_name in groups:
            return True
        else:
            return False

    def article_exists(self, group_name, style, range):
        pass

    def get_first_article(self, group_name):
        return 1

    def get_group_stats(self, filename):
        mbox = self.get_mailbox(filename)
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
        result = self.get_group_stats(group_name.replace('papercut.mbox.', ''))
        return (result[0], result[2], result[1])

    def get_LIST(self):
        result = self.get_file_list()
        if len(result) == 0:
            return ""
        else:
            groups = []
            for mbox in result:
                total, maximum, minimum = self.get_group_stats(mbox)
                if settings.server_type == 'read-only':
                    groups.append("papercut.mbox.%s %s %s n" % (mbox, maximum, minimum))
                else:
                    groups.append("papercut.mbox.%s %s %s y" % (mbox, maximum, minimum))
            return "\r\n".join(groups)

    def get_STAT(self, group_name, id):
        # basically check if the message exists
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
            if msg == None:
                return None
            if i == int(id):
                return ("\r\n".join(msg.headers), msg.fp.read())
            i = i + 1

    def get_LAST(self, group_name, current_id):
        pass

    def get_NEXT(self, group_name, current_id):
        pass

    def get_HEAD(self, group_name, id):
        pass

    def get_BODY(self, group_name, id):
        pass

    def get_XOVER(self, group_name, start_id, end_id='ggg'):
        pass

    def get_XPAT(self, group_name, header, pattern, start_id, end_id='ggg'):
        pass

    def get_LISTGROUP(self, group_name):
        pass

    def get_XGTITLE(self, pattern=None):
        pass

    def get_XHDR(self, group_name, header, style, range):
        pass

    def do_POST(self, group_name, lines, ip_address, username=''):
        # let's make the mbox storage always read-only for now
        return None
