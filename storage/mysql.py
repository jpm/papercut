#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: mysql.py,v 1.42 2004-02-01 05:23:13 jpm Exp $
import MySQLdb
import time
import re
import settings
import strutil
import mime

# we don't need to compile the regexps everytime..
singleline_regexp = re.compile("^\.", re.M)
from_regexp = re.compile("^From:(.*)", re.M)
subject_regexp = re.compile("^Subject:(.*)", re.M)
references_regexp = re.compile("^References:(.*)<(.*)>", re.M)

class Papercut_Storage:
    """
    Storage Backend interface for saving the article information in a MySQL database.

    This is not a storage to implement a web board -> nntp gateway, but a standalone nntp server.
    """

    def __init__(self):
        self.conn = MySQLdb.connect(host=settings.dbhost, db=settings.dbname, user=settings.dbuser, passwd=settings.dbpass)
        self.cursor = self.conn.cursor()

    def quote_string(self, text):
        """Quotes strings the MySQL way."""
        return text.replace("'", "\\'")

    def get_body(self, lines):
        pass

    def get_header(self, lines):
        pass

    def group_exists(self, group_name):
        stmt = """
                SELECT
                    COUNT(*) AS check
                FROM
                    papercut_groups
                WHERE
                    LOWER(name)=LOWER('%s')""" % (group_name)
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def article_exists(self, group_name, style, range):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    COUNT(*) AS check
                FROM
                    %s
                WHERE
                    """ % (table_name)
        if style == 'range':
            stmt = "%s id > %s" % (stmt, range[0])
            if len(range) == 2:
                stmt = "%s AND id < %s" % (stmt, range[1])
        else:
            stmt = "%s id = %s" % (stmt, range[0])
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def get_first_article(self, group_name):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    IF(MIN(id) IS NULL, 0, MIN(id)) AS first_article
                FROM
                    %s""" % (table_name)
        num_rows = self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def get_group_stats(self, group_name):
        total, max, min = self.get_table_stats(self.get_table_name(group_name))
        return (total, min, max, group_name)

    def get_table_stats(self, table_name):
        stmt = """
                SELECT
                   COUNT(id) AS total,
                   IF(MAX(id) IS NULL, 0, MAX(id)) AS maximum,
                   IF(MIN(id) IS NULL, 0, MIN(id)) AS minimum
                FROM
                    %s""" % (table_name)
        num_rows = self.cursor.execute(stmt)
        return self.cursor.fetchone()

    def get_table_name(self, group_name):
        stmt = """
                SELECT
                    table_name
                FROM
                    papercut_groups
                WHERE
                    name='%s'""" % (group_name.replace('*', '%'))
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def get_message_id(self, msg_num, group):
        return '<%s@%s>' % (msg_num, group)

    def get_NEWGROUPS(self, ts, group='%'):
        stmt = """
                SELECT
                    name
                FROM
                    papercut_groups
                WHERE
                    name LIKE '%%%s' 
                ORDER BY
                    name ASC""" % (group)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        if len(result) == 0:
            return None
        else:
            return "\r\n".join(["%s" % k for k in result])

    def get_NEWNEWS(self, ts, group='*'):
        stmt = """
                SELECT
                    name,
                    table_name
                FROM
                    papercut_groups
                WHERE
                    name='%s'
                ORDER BY
                    name ASC""" % (group_name.replace('*', '%'))
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        articles = []
        for group, table in result:
            stmt = """
                    SELECT
                        id
                    FROM
                        %s
                    WHERE
                        UNIX_TIMESTAMP(datestamp) >= %s""" % (table, ts)
            num_rows = self.cursor.execute(stmt)
            if num_rows == 0:
                continue
            ids = list(self.cursor.fetchall())
            for id in ids:
                articles.append("<%s@%s>" % (id, group))
        if len(articles) == 0:
            return ''
        else:
            return "\r\n".join(articles)

    def get_GROUP(self, group_name):
        table_name = self.get_table_name(group_name)
        result = self.get_table_stats(table_name)
        return (result[0], result[2], result[1])

    def get_LIST(self):
        stmt = """
                SELECT
                    name,
                    table_name
                FROM
                    papercut_groups
                WHERE
                    LENGTH(name) > 0
                ORDER BY
                    name ASC"""
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        if len(result) == 0:
            return ""
        else:
            lists = []
            for group_name, table in result:
                total, maximum, minimum = self.get_table_stats(table)
                if settings.server_type == 'read-only':
                    lists.append("%s %s %s n" % (group_name, maximum, minimum))
                else:
                    lists.append("%s %s %s y" % (group_name, maximum, minimum))
            return "\r\n".join(lists)

    def get_STAT(self, group_name, id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id
                FROM
                    %s
                WHERE
                    id=%s""" % (table_name, id)
        return self.cursor.execute(stmt)

    def get_ARTICLE(self, group_name, id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id,
                    author,
                    subject,
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
                    body,
                    parent
                FROM
                    %s
                WHERE
                    id=%s""" % (table_name, id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        result = list(self.cursor.fetchone())
        headers = []
        headers.append("Path: %s" % (settings.nntp_hostname))
        headers.append("From: %s" % (result[1]))
        headers.append("Newsgroups: %s" % (group_name))
        headers.append("Date: %s" % (strutil.get_formatted_time(time.localtime(result[3]))))
        headers.append("Subject: %s" % (result[2]))
        headers.append("Message-ID: <%s@%s>" % (result[0], group_name))
        headers.append("Xref: %s %s:%s" % (settings.nntp_hostname, group_name, result[0]))
        if result[5] != 0:
            headers.append("References: <%s@%s>" % (result[5], group_name))
        return ("\r\n".join(headers), strutil.format_body(result[4]))

    def get_LAST(self, group_name, current_id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id
                FROM
                    %s
                WHERE
                    id < %s
                ORDER BY
                    id DESC
                LIMIT 0, 1""" % (table_name, current_id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        return self.cursor.fetchone()[0]

    def get_NEXT(self, group_name, current_id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id
                FROM
                    %s
                WHERE
                    id > %s
                ORDER BY
                    id ASC
                LIMIT 0, 1""" % (table_name, current_id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        return self.cursor.fetchone()[0]

    def get_HEAD(self, group_name, id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id,
                    author,
                    subject,
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
                    parent
                FROM
                    %s
                WHERE
                    id=%s""" % (table_name, id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        result = list(self.cursor.fetchone())
        headers = []
        headers.append("Path: %s" % (settings.nntp_hostname))
        headers.append("From: %s" % (result[1]))
        headers.append("Newsgroups: %s" % (group_name))
        headers.append("Date: %s" % (strutil.get_formatted_time(time.localtime(result[3]))))
        headers.append("Subject: %s" % (result[2]))
        headers.append("Message-ID: <%s@%s>" % (result[0], group_name))
        headers.append("Xref: %s %s:%s" % (settings.nntp_hostname, group_name, result[0]))
        if result[4] != 0:
            headers.append("References: <%s@%s>" % (result[4], group_name))
        return "\r\n".join(headers)

    def get_BODY(self, group_name, id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    body
                FROM
                    %s
                WHERE
                    id=%s""" % (table_name, id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        else:
            return strutil.format_body(self.cursor.fetchone()[0])

    def get_XOVER(self, group_name, start_id, end_id='ggg'):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id,
                    parent,
                    author,
                    subject,
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
                    body,
                    line_num,
                    bytes
                FROM
                    %s
                WHERE
                    id >= %s""" % (table_name, start_id)
        if end_id != 'ggg':
            stmt = "%s AND id <= %s" % (stmt, end_id)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        overviews = []
        for row in result:
            message_id = "<%s@%s>" % (row[0], group_name)
            xref = 'Xref: %s %s:%s' % (settings.nntp_hostname, group_name, row[0])
            if row[1] != 0:
                reference = "<%s@%s>" % (row[1], group_name)
            else:
                reference = ""
            # message_number <tab> subject <tab> author <tab> date <tab> message_id <tab> reference <tab> bytes <tab> lines <tab> xref
            overviews.append("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (row[0], row[3], row[2], strutil.get_formatted_time(time.localtime(row[4])), message_id, reference, row[7], row[6], xref))
        return "\r\n".join(overviews)

    def get_XPAT(self, group_name, header, pattern, start_id, end_id='ggg'):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id,
                    parent,
                    author,
                    subject,
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
                    bytes,
                    line_num
                FROM
                    %s
                WHERE
                    id >= %s AND""" % (table_name, header, strutil.format_wildcards(pattern), start_id)
        if header.upper() == 'SUBJECT':
            stmt = "%s AND subject REGEXP '%s'" % (stmt, strutil.format_wildcards(pattern))
        elif header.upper() == 'FROM':
            stmt = "%s AND (author REGEXP '%s' OR email REGEXP '%s')" % (stmt, strutil.format_wildcards(pattern), strutil.format_wildcards(pattern))
        elif header.upper() == 'DATE':
            stmt = "%s AND %s" % (stmt, pattern)
        if end_id != 'ggg':
            stmt = "%s AND id <= %s" % (stmt, end_id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        result = list(self.cursor.fetchall())
        hdrs = []
        for row in result:
            if header.upper() == 'SUBJECT':
                hdrs.append('%s %s' % (row[0], row[3]))
            elif header.upper() == 'FROM':
                hdrs.append('%s %s' % (row[0], row[2]))
            elif header.upper() == 'DATE':
                hdrs.append('%s %s' % (row[0], strutil.get_formatted_time(time.localtime(result[4]))))
            elif header.upper() == 'MESSAGE-ID':
                hdrs.append('%s <%s@%s>' % (row[0], row[0], group_name))
            elif (header.upper() == 'REFERENCES') and (row[1] != 0):
                hdrs.append('%s <%s@%s>' % (row[0], row[1], group_name))
            elif header.upper() == 'BYTES':
                hdrs.append('%s %s' % (row[0], row[5]))
            elif header.upper() == 'LINES':
                hdrs.append('%s %s' % (row[0], row[6]))
            elif header.upper() == 'XREF':
                hdrs.append('%s %s %s:%s' % (row[0], settings.nntp_hostname, group_name, row[0]))
        if len(hdrs) == 0:
            return ""
        else:
            return "\r\n".join(hdrs)

    def get_LISTGROUP(self, group_name):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id
                FROM
                    %s
                ORDER BY
                    id ASC""" % (table_name)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        return "\r\n".join(["%s" % k for k in result])

    def get_XGTITLE(self, pattern=None):
        stmt = """
                SELECT
                    name,
                    description
                FROM
                    papercut_groups
                WHERE
                    LENGTH(name) > 0"""
        if pattern != None:
            stmt = stmt + """ AND
                    name REGEXP '%s'""" % (strutil.format_wildcards(pattern))
        stmt = stmt + """
                ORDER BY
                    name ASC"""
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        return "\r\n".join(["%s %s" % (k, v) for k, v in result])

    def get_XHDR(self, group_name, header, style, range):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id,
                    parent,
                    author,
                    subject,
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
                    bytes,
                    line_num
                FROM
                    %s
                WHERE
                    """ % (table_name)
        if style == 'range':
            stmt = '%s id >= %s' % (stmt, range[0])
            if len(range) == 2:
                stmt = '%s AND id <= %s' % (stmt, range[1])
        else:
            stmt = '%s id = %s' % (stmt, range[0])
        if self.cursor.execute(stmt) == 0:
            return None
        result = self.cursor.fetchall()
        hdrs = []
        for row in result:
            if header.upper() == 'SUBJECT':
                hdrs.append('%s %s' % (row[0], row[3]))
            elif header.upper() == 'FROM':
                hdrs.append('%s %s' % (row[0], row[2]))
            elif header.upper() == 'DATE':
                hdrs.append('%s %s' % (row[0], strutil.get_formatted_time(time.localtime(result[4]))))
            elif header.upper() == 'MESSAGE-ID':
                hdrs.append('%s <%s@%s>' % (row[0], row[0], group_name))
            elif (header.upper() == 'REFERENCES') and (row[1] != 0):
                hdrs.append('%s <%s@%s>' % (row[0], row[1], group_name))
            elif header.upper() == 'BYTES':
                hdrs.append('%s %s' % (row[0], row[6]))
            elif header.upper() == 'LINES':
                hdrs.append('%s %s' % (row[0], row[7]))
            elif header.upper() == 'XREF':
                hdrs.append('%s %s %s:%s' % (row[0], settings.nntp_hostname, group_name, row[0]))
        if len(hdrs) == 0:
            return ""
        else:
            return "\r\n".join(hdrs)

    def do_POST(self, group_name, body, ip_address, username=''):
        table_name = self.get_table_name(group_name)
        author = from_regexp.search(body, 0).groups()[0].strip()
        subject = subject_regexp.search(body, 0).groups()[0].strip()
        if body.find('References') != -1:
            references = references_regexp.search(body, 0).groups()
            parent_id, void = references[-1].strip().split('@')
            stmt = """
                    SELECT
                        IF(MAX(id) IS NULL, 1, MAX(id)+1) AS next_id
                    FROM
                        %s""" % (table_name)
            num_rows = self.cursor.execute(stmt)
            if num_rows == 0:
                new_id = 1
            else:
                new_id = self.cursor.fetchone()[0]
            stmt = """
                    SELECT
                        id,
                        thread
                    FROM
                        %s
                    WHERE
                        id=%s
                    GROUP BY
                        id""" % (table_name, parent_id)
            num_rows = self.cursor.execute(stmt)
            if num_rows == 0:
                return None
            parent_id, thread_id = self.cursor.fetchone()
        else:
            stmt = """
                    SELECT
                        IF(MAX(id) IS NULL, 1, MAX(id)+1) AS next_id
                    FROM
                        %s""" % (table_name)
            self.cursor.execute(stmt)
            new_id = self.cursor.fetchone()[0]
            parent_id = 0
            thread_id = new_id
        body = mime.get_body(body)
        stmt = """
                INSERT INTO
                    %s
                (
                    id,
                    datestamp,
                    thread,
                    parent,
                    author,
                    subject,
                    host,
                    body,
                    bytes,
                    line_num
                ) VALUES (
                    %s,
                    NOW(),
                    %s,
                    %s,
                    '%s',
                    '%s',
                    '%s',
                    '%s',
                    %s,
                    %s
                )
                """ % (table_name, new_id, thread_id, parent_id, self.quote_string(author), self.quote_string(subject), ip_address, self.quote_string(body), len(body), len(body.split('\n')))
        if not self.cursor.execute(stmt):
            return None
        else:
            return 1
