#!/usr/bin/env python
# Copyright (c) 2001 Joao Prado Maia. See the LICENSE file for more information.
# $Id: mysql.py,v 1.19 2002-01-13 07:35:39 jpm Exp $
import MySQLdb
import time
from mimify import mime_encode_header, mime_decode_header
import re
import rfc822
import sys
import settings

class Papercut_Backend:

    def __init__(self):
        print 'Connecting to the MySQL server...'
        self.conn = MySQLdb.connect(db=settings.dbname, user=settings.dbuser, passwd=settings.dbpass)
        self.cursor = self.conn.cursor()

    def get_message_body(self, headers):
        body = []
        found = 0
        raw_headers = headers.split('\r\n')
        for line in raw_headers:
            if not found and line == '':
                found = 1
                continue
            if found:
                body.append(line)
        return "\r\n".join(body)

    def get_formatted_time(self, time_tuple):
        return time.strftime('%a, %d %B %Y %H:%M:%S %Z', time_tuple)

    def format_body(self, text):
        return re.compile("^\.", re.M).sub("..", text)

    def format_wildcards(self, pattern):
        pattern.replace('*', '.*')
        pattern.replace('?', '.*')
        return pattern

    def group_exists(self, group_name):
        stmt = """
                SELECT
                    COUNT(*) AS check
                FROM
                    forum.forums
                WHERE
                    nntp_group_name='%s'""" % (group_name)
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def article_exists(self, group_name, style, range):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    COUNT(*) AS check
                FROM
                    forum.%s
                WHERE""" % (table_name)
        if style == 'range':
            stmt = "%s id > %s" % (stmt, range[0])
            if len(range) == 2:
                stmt = "%s AND id < %s" % (stmt, range[1])
        else:
            stmt = "%s id = %s" % (stmt, range[0])
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def get_group_stats(self, table_name):
        stmt = """
                SELECT
                   COUNT(id) AS total,
                   MIN(id) AS maximum,
                   MAX(id) AS minimum
                FROM
                    forum.%s""" % (table_name)
        self.cursor.execute(stmt)
        return self.cursor.fetchone()

    def get_table_name(self, group_name):
        stmt = """
                SELECT
                    table_name
                FROM
                    forum.forums
                WHERE
                    nntp_group_name='%s'""" % (group_name.replace('*', '%'))
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]
        
    def get_NEWGROUPS(self, ts, group='%'):
        stmt = """
                SELECT
                    nntp_group_name
                FROM
                    forum.forums
                WHERE
                    nntp_group_name LIKE '%%%s'
                ORDER BY
                    nntp_group_name ASC""" % (group)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        if len(result) == 0:
            return None
        else:
            return "\r\n".join(["%s" % k for k in result])

    def get_NEWNEWS(self, ts, group='*'):
        stmt = """
                SELECT
                    nntp_group_name,
                    table_name
                FROM
                    forum.forums
                WHERE
                    nntp_group_name='%s'
                ORDER BY
                    nntp_group_name ASC""" % (group_name.replace('*', '%'))
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        articles = []
        for group, table in result:
            stmt = """
                    SELECT
                        id
                    FROM
                        forum.%s
                    WHERE
                        UNIX_TIMESTAMP(datestamp) >= %s""" % (table, ts)
            self.cursor.execute(stmt)
            ids = list(self.cursor.fetchall())
            for id in ids:
                articles.append("<%s@%s>" % (id, group))
        return "\r\n".join(["%s" % k for k in articles])

    def get_GROUP(self, group_name):
        table_name = self.get_table_name(group_name)
        result = self.get_group_stats(table_name)
        return (result[0], result[1], result[2])

    def get_LIST(self):
        stmt = """
                SELECT
                    nntp_group_name,
                    table_name
                FROM
                    forum.forums
                ORDER BY
                    nntp_group_name ASC"""
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        if len(result) == 0:
            return None
        return result

    def get_STAT(self, group_name, id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id
                FROM
                    forum.%s
                WHERE
                    id=%s""" % (table_name, id)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchone())
        return len(result)

    def get_ARTICLE(self, group_name, id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    A.id,
                    author,
                    email,
                    subject,
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
                    body
                FROM
                    forum.%s A,
                    forum.%s_bodies B
                WHERE
                    A.id=B.id AND
                    A.id=%s""" % (table_name, table_name, id)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchone())
        if len(result[2]) == 0:
            author = result[1]
        else:
            author = "%s <%s>" % (result[1], result[2])
        formatted_time = self.get_formatted_time(time.localtime(result[4]))
        head = "From: %s\r\nNewsgroups: %s\r\nDate: %s\r\nSubject: %s\r\nMessage-ID: <%s@%s>" % (author, group_name, formatted_time, result[3], result[0], group_name)
        return (head, self.format_body(result[5]))

    def get_LAST(self, group_name, current_id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id
                FROM
                    forum.%s
                WHERE
                    id < %s
                ORDER BY
                    id DESC
                LIMIT 0, 1""" % (table_name, current_id)
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def get_NEXT(self, group_name, current_id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id
                FROM
                    forum.%s
                WHERE
                    id > %s
                ORDER BY
                    id ASC
                LIMIT 0, 1""" % (table_name, current_id)
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def get_HEAD(self, group_name, id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id,
                    author,
                    email,
                    subject,
                    UNIX_TIMESTAMP(datestamp) AS datestamp
                FROM
                    forum.%s
                WHERE
                    id=%s""" % (table_name, id)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchone())
        if len(result[2]) == 0:
            author = result[1]
        else:
            author = "%s <%s>" % (result[1], result[2])
        formatted_time = self.get_formatted_time(time.localtime(result[4]))
        head = "From: %s\r\nNewsgroups: %s\r\nDate: %s\r\nSubject: %s\r\nMessage-ID: <%s@%s>\r\nReferences: %s" % (author, group_name, formatted_time, result[3], result[0], group_name)
        return head

    def get_BODY(self, group_name, id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    body
                FROM
                    forum.%s_bodies
                WHERE
                    id=%s""" % (table_name, id)
        self.cursor.execute(stmt)
        return self.format_body(self.cursor.fetchone()[0])

    def get_XOVER(self, group_name, start_id, end_id='ggg'):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    A.id,
                    parent,
                    author,
                    email,
                    subject,
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
                    B.body
                FROM
                    forum.%s A, 
                    forum.%s_bodies B
                WHERE
                    A.id=B.id AND
                    A.id >= %s""" % (table_name, table_name, start_id)
        if end_id != 'ggg':
            stmt = "%s AND A.id <= %s" % (stmt, end_id)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        overviews = []
        for row in result:
            if row[3] == '':
                author = row[2]
            else:
                author = "%s <%s>" % (row[2], row[3])
            formatted_time = self.get_formatted_time(time.localtime(row[5]))
            message_id = "<%s@%s>" % (row[0], group_name)
            line_count = len(row[6].split('\n'))
            xref = 'Xref: %s:%s' % (group_name, row[1])
            overviews.append("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (row[0], row[4], author, formatted_time, message_id, row[1], len(self.format_body(row[6])), line_count, xref))
        return "\r\n".join(["%s" % k for k in overviews])

    def get_XPAT(self, group_name, header, pattern, start_id, end_id='ggg'):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    A.id,
                    parent,
                    author,
                    email,
                    subject,
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
                    B.body
                FROM
                    forum.%s A, 
                    forum.%s_bodies B
                WHERE
                    %s REGEXP '%s'
                    A.id=B.id AND
                    A.id >= %s""" % (table_name, table_name, header, self.format_wildcards(pattern), start_id)
        if end_id != 'ggg':
            stmt = "%s AND A.id <= %s" % (stmt, end_id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        result = list(self.cursor.fetchall())
        overviews = []
        for row in result:
            if row[3] == '':
                author = row[2]
            else:
                author = "%s <%s>" % (row[2], row[3])
            formatted_time = self.get_formatted_time(time.localtime(row[5]))
            message_id = "<%s@%s>" % (row[0], group_name)
            line_count = len(row[6].split('\n'))
            overviews.append("%s\t%s\t%s\t%s\t%s\t%s\t%s" % (row[0], row[4], author, formatted_time, message_id, row[1], len(self.format_body(row[6])), line_count))
        return "\r\n".join(["%s" % k for k in overviews])

    def get_LISTGROUP(self, group_name):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id
                FROM
                    forum.%s
                ORDER BY
                    id ASC""" % (table_name)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        return "\r\n".join(["%s" % k for k in result])

    def get_XGTITLE(self, pattern):
        stmt = """
                SELECT
                    nntp_group_name,
                    description
                FROM
                    forum.forums
                WHERE
                    nntp_group_name REGEXP '%s'
                ORDER BY
                    nntp_group_name ASC""" % (self.format_wildcards(pattern))
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        return "\r\n".join(["%s %s" % (k, v) for k, v in result])

    def get_XHDR(self, group_name, header, style, range):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    A.id,
                    parent,
                    author,
                    email,
                    subject,
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
                    B.body
                FROM
                    forum.%s
                WHERE""" % (table_name)
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
            if header == 'SUBJECT':
                hdrs.append('%s %s' % (row[0], row[3]))
            elif header == 'FROM':
                hdrs.append('%s %s <%s>' % (row[0], row[1], row[2]))
        return "\r\n".join(["%s" % k for k in hdrs])

    def do_POST(self, group_name, lines, ip_address):
        table_name = self.get_table_name(group_name)
        body = self.get_message_body(lines)
        author, email = re.compile("^From:(.*)<(.*)>", re.M).search(lines, 1).groups()
        subject = re.compile("^Subject:(.*)", re.M).search(lines, 1).groups()[0].strip()
        if lines.find('References') != -1:
            # get the 'modifystamp' value from the parent (if any)
            references = re.compile("^References: <(.*)>", re.M).search(lines, 1).groups()[0].strip()
            parent_id, void = references.split('@')
            stmt = """
                    SELECT
                        MAX(id)+1
                    FROM
                        forum.%s""" % (table_name)
            self.cursor.execute(stmt)
            new_id = self.cursor.fetchone()[0]
            stmt = """
                    SELECT
                        id,
                        thread,
                        modifystamp
                    FROM
                        forum.%s
                    WHERE
                        id=%s
                    GROUP BY
                        id""" % (table_name, parent_id)
            num_rows = self.cursor.execute(stmt)
            if num_rows == 0:
                return None
            parent_id, thread_id, modifystamp = self.cursor.fetchone()
        else:
            stmt = """
                    SELECT
                        MAX(id)+1,
                        UNIX_TIMESTAMP()
                    FROM
                        forum.%s
                    GROUP BY
                        id""" % (table_name)
            self.cursor.execute(stmt)
            new_id, modifystamp = self.cursor.fetchone()
            parent_id = 0
            thread_id = new_id
        stmt = """
                INSERT INTO
                    forum.%s
                (
                    id,
                    datestamp,
                    thread,
                    parent,
                    author,
                    subject,
                    email,
                    host,
                    email_reply,
                    approved,
                    msgid,
                    modifystamp,
                    userid
                ) VALUES (
                    %s,
                    NOW(),
                    %s,
                    %s,
                    '%s',
                    '%s',
                    '%s',
                    '%s',
                    'N',
                    'Y',
                    '',
                    %s,
                    0
                )
                """ % (table_name, new_id, thread_id, parent_id, author.strip(), subject, email, ip_address, modifystamp)
        if not self.cursor.execute(stmt):
            return None
        else:
            # insert into the '*_bodies' table
            stmt = """
                    INSERT INTO
                        forum.%s_bodies
                    (
                        id,
                        body,
                        thread
                    ) VALUES (
                        %s,
                        '%s',
                        %s
                    )""" % (table_name, new_id, body, thread_id)
            if not self.cursor.execute(stmt):
                # delete from 'table_name' before returning..
                stmt = """
                        DELETE FROM
                            forum.%s
                        WHERE
                            id=%s""" % (table_name, new_id)
                self.cursor.execute(stmt)
                return None
            else:
                return 1
