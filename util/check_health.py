#!/usr/bin/env python
# Copyright (c) 2004 Joao Prado Maia. See the LICENSE file for more information.
# $Id: check_health.py,v 1.1 2004-01-25 06:10:33 jpm Exp $

import settings
from nntplib import NNTP

s = NNTP(settings.nntp_hostname, settings.nntp_port)
resp, groups = s.list()
# check all of the groups, just in case
for group_name, last, first, flag in groups:
    resp, count, first, last, name = s.group(group_name)
    print "\nGroup", group_name, 'has', count, 'articles, range', first, 'to', last
    resp, subs = s.xhdr('subject', first + '-' + last)
    for id, sub in subs[-10:]:
        print id, sub
s.quit()
