#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: phpbb_mysql.py,v 1.7 2002-12-13 07:34:38 jpm Exp $
import MySQLdb
import time
from mimify import mime_encode_header
import re
import settings
import md5
import binascii
import mime
import strutil

# we don't need to compile the regexps everytime..
doubleline_regexp = re.compile("^\.\.", re.M)
singleline_regexp = re.compile("^\.", re.M)
from_regexp = re.compile("^From:(.*)<(.*)>", re.M)
subject_regexp = re.compile("^Subject:(.*)", re.M)
references_regexp = re.compile("^References:(.*)<(.*)>", re.M)
lines_regexp = re.compile("^Lines:(.*)", re.M)

class Papercut_Storage:
    """
    Storage Backend interface for the Phorum web message board software (http://phorum.org)
    
    This is the interface for Phorum running on a MySQL database. For more information
    on the structure of the 'storage' package, please refer to the __init__.py
    available on the 'storage' sub-directory.
    """

    def __init__(self):
        self.conn = MySQLdb.connect(host=settings.dbhost, db=settings.dbname, user=settings.dbuser, passwd=settings.dbpass)
        self.cursor = self.conn.cursor()

    def get_message_body(self, headers):
        """Parses and returns the most appropriate message body possible.
        
        The function tries to extract the plaintext version of a MIME based
        message, and if it is not available then it returns the html version.        
        """
        return mime.get_text_message(headers)

    def quote_string(self, text):
        """Quotes strings the MySQL way."""
        return text.replace("'", "\\'")

    def make_bbcode_uid(self):
        return binascii.hexlify(md5.new(str(time.clock())).digest())

    def encode_ip(self, dotquad_ip):
        t = dotquad_ip.split('.')
        return '%02x%02x%02x%02x' % (int(t[0]), int(t[1]), int(t[2]), int(t[3]))

    def group_exists(self, group_name):
        stmt = """
                SELECT
                    COUNT(*) AS check
                FROM
                    %sforums
                WHERE
                    nntp_group_name='%s'""" % (settings.phpbb_table_prefix, group_name)
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def article_exists(self, group_name, style, range):
        forum_id = self.get_forum(group_name)
        stmt = """
                SELECT
                    COUNT(*) AS check
                FROM
                    %sposts
                WHERE
                    forum_id=%s""" % (settings.phpbb_table_prefix, forum_id)
        if style == 'range':
            stmt = "%s AND post_id > %s" % (stmt, range[0])
            if len(range) == 2:
                stmt = "%s AND post_id < %s" % (stmt, range[1])
        else:
            stmt = "%s AND post_id = %s" % (stmt, range[0])
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def get_first_article(self, group_name):
        forum_id = self.get_forum(group_name)
        stmt = """
                SELECT
                    IF(MIN(post_id) IS NULL, 0, MIN(post_id)) AS first_article
                FROM
                    %sposts
                WHERE
                    forum_id=%s""" % (settings.phpbb_table_prefix, forum_id)
        num_rows = self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def get_group_stats(self, forum_id):
        stmt = """
                SELECT
                   COUNT(post_id) AS total,
                   IF(MAX(post_id) IS NULL, 0, MAX(post_id)) AS maximum,
                   IF(MIN(post_id) IS NULL, 0, MIN(post_id)) AS minimum
                FROM
                    %sposts
                WHERE
                    forum_id=%s""" % (settings.phpbb_table_prefix, forum_id)
        num_rows = self.cursor.execute(stmt)
        return self.cursor.fetchone()

    def get_forum(self, group_name):
        stmt = """
                SELECT
                    forum_id
                FROM
                    %sforums
                WHERE
                    nntp_group_name='%s'""" % (settings.phpbb_table_prefix, group_name)
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def get_message_id(self, msg_num, group):
        return '<%s@%s>' % (msg_num, group)

    def get_NEWGROUPS(self, ts, group='%'):
        stmt = """
                SELECT
                    nntp_group_name
                FROM
                    %sforums
                WHERE
                    nntp_group_name LIKE '%%%s' 
                ORDER BY
                    nntp_group_name ASC""" % (settings.phpbb_table_prefix, group)
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
                    forum_id
                FROM
                    %sforums
                WHERE
                    nntp_group_name='%s'
                ORDER BY
                    nntp_group_name ASC""" % (settings.phpbb_table_prefix, group_name)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        articles = []
        for group, forum_id in result:
            stmt = """
                    SELECT
                        post_id
                    FROM
                        %sposts
                    WHERE
                        forum_id=%s AND
                        post_time >= %s""" % (forum_id, ts)
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
        forum_id = self.get_forum(group_name)
        result = self.get_group_stats(forum_id)
        return (result[0], result[2], result[1])

    def get_LIST(self):
        stmt = """
                SELECT
                    nntp_group_name,
                    forum_id
                FROM
                    %sforums
                WHERE
                    LENGTH(nntp_group_name) > 0
                ORDER BY
                    nntp_group_name ASC""" % (settings.phpbb_table_prefix)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        if len(result) == 0:
            return ""
        else:
            lists = []
            for group_name, forum_id in result:
                total, maximum, minimum = self.get_group_stats(forum_id)
                if settings.server_type == 'read-only':
                    lists.append("%s %s %s n" % (group_name, maximum, minimum))
                else:
                    lists.append("%s %s %s y" % (group_name, maximum, minimum))
            return "\r\n".join(lists)

    def get_STAT(self, group_name, id):
        forum_id = self.get_forum(group_name)
        stmt = """
                SELECT
                    id
                FROM
                    %sposts
                WHERE
                    forum_id=%s AND
                    id=%s""" % (settings.phpbb_table_prefix, forum_id, id)
        return self.cursor.execute(stmt)

    def get_ARTICLE(self, group_name, id):
        forum_id = self.get_forum(group_name)
        prefix = settings.phpbb_table_prefix
        stmt = """
                SELECT
                    A.post_id,
                    C.username,
                    C.user_email,
                    B.post_subject,
                    A.post_time,
                    B.post_text,
                    A.topic_id,
                    A.post_username,
                    MIN(D.post_id)
                FROM
                    %sposts A,
                    %sposts_text B
                INNER JOIN
                    %sposts D
                ON
                    D.topic_id=A.topic_id
                LEFT JOIN
                    %susers C
                ON
                    A.poster_id=C.user_id
                WHERE
                    A.forum_id=%s AND
                    A.post_id=B.post_id AND
                    A.post_id=%s
                GROUP BY
                    D.topic_id""" % (prefix, prefix, prefix, prefix, forum_id, id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        result = list(self.cursor.fetchone())
        # check if there is a registered user
        if result[7] == '':
            if len(result[2]) == 0:
                author = result[1]
            else:
                author = "%s <%s>" % (result[1], result[2])
        else:
            author = result[7]
        formatted_time = strutil.get_formatted_time(time.localtime(result[4]))
        headers = []
        headers.append("Path: %s" % (settings.nntp_hostname))
        headers.append("From: %s" % (author))
        headers.append("Newsgroups: %s" % (group_name))
        headers.append("Date: %s" % (formatted_time))
        headers.append("Subject: %s" % (result[3]))
        headers.append("Message-ID: <%s@%s>" % (result[0], group_name))
        headers.append("Xref: %s %s:%s" % (settings.nntp_hostname, group_name, result[0]))
        if result[8] != result[0]:
            headers.append("References: <%s@%s>" % (result[8], group_name))
        return ("\r\n".join(headers), strutil.format_body(result[5]))

    def get_LAST(self, group_name, current_id):
        forum_id = self.get_forum(group_name)
        stmt = """
                SELECT
                    post_id
                FROM
                    %sposts
                WHERE
                    post_id < %s AND
                    forum_id=%s
                ORDER BY
                    post_id DESC
                LIMIT 0, 1""" % (settings.phpbb_table_prefix, current_id, forum_id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        return self.cursor.fetchone()[0]

    def get_NEXT(self, group_name, current_id):
        forum_id = self.get_forum(group_name)
        stmt = """
                SELECT
                    post_id
                FROM
                    %sposts
                WHERE
                    forum_id=%s AND
                    post_id > %s
                ORDER BY
                    post_id ASC
                LIMIT 0, 1""" % (settings.phpbb_table_prefix, forum_id, current_id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        return self.cursor.fetchone()[0]

    def get_HEAD(self, group_name, id):
        forum_id = self.get_forum(group_name)
        prefix = settings.phpbb_table_prefix
        stmt = """
                SELECT
                    A.post_id,
                    C.username,
                    C.user_email,
                    B.post_subject,
                    A.post_time,
                    A.topic_id,
                    A.post_username,
                    MIN(D.post_id)
                FROM
                    %sposts A,
                    %sposts_text B
                INNER JOIN
                    %sposts D
                ON
                    D.topic_id=A.topic_id
                LEFT JOIN
                    %susers C
                ON
                    A.poster_id=C.user_id
                WHERE
                    A.forum_id=%s AND
                    A.post_id=B.post_id AND
                    A.post_id=%s
                GROUP BY
                    D.topic_id""" % (prefix, prefix, prefix, prefix, forum_id, id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        result = list(self.cursor.fetchone())
        # check if there is a registered user
        if len(result[6]) == 0:
            if len(result[2]) == 0:
                author = result[1]
            else:
                author = "%s <%s>" % (result[1], result[2])
        else:
            author = result[6]
        formatted_time = strutil.get_formatted_time(time.localtime(result[4]))
        headers = []
        headers.append("Path: %s" % (settings.nntp_hostname))
        headers.append("From: %s" % (author))
        headers.append("Newsgroups: %s" % (group_name))
        headers.append("Date: %s" % (formatted_time))
        headers.append("Subject: %s" % (result[3]))
        headers.append("Message-ID: <%s@%s>" % (result[0], group_name))
        headers.append("Xref: %s %s:%s" % (settings.nntp_hostname, group_name, result[0]))
        if result[7] != result[0]:
            headers.append("References: <%s@%s>" % (result[7], group_name))
        return "\r\n".join(headers)

    def get_BODY(self, group_name, id):
        forum_id = self.get_forum(group_name)
        prefix = settings.phpbb_table_prefix
        stmt = """
                SELECT
                    B.post_text
                FROM
                    %sposts A,
                    %sposts_text B
                WHERE
                    A.post_id=B.post_id AND
                    A.forum_id=%s AND
                    A.post_id=%s""" % (prefix, prefix, forum_id, id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        else:
            return strutil.format_body(self.cursor.fetchone()[0])

    def get_XOVER(self, group_name, start_id, end_id='ggg'):
        forum_id = self.get_forum(group_name)
        prefix = settings.phpbb_table_prefix
        stmt = """
                SELECT
                    A.post_id,
                    A.topic_id,
                    C.username,
                    C.user_email,
                    B.post_subject,
                    A.post_time,
                    B.post_text,
                    A.post_username
                FROM
                    %sposts A, 
                    %sposts_text B
                LEFT JOIN
                    %susers C
                ON
                    A.poster_id=C.user_id
                WHERE
                    A.post_id=B.post_id AND
                    A.forum_id=%s AND
                    A.post_id >= %s""" % (prefix, prefix, prefix, forum_id, start_id)
        if end_id != 'ggg':
            stmt = "%s AND A.post_id <= %s" % (stmt, end_id)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        overviews = []
        for row in result:
            if row[7] == '':
                if row[3] == '':
                    author = row[2]
                else:
                    author = "%s <%s>" % (row[2], row[3])
            else:
                author = row[7]
            formatted_time = strutil.get_formatted_time(time.localtime(row[5]))
            message_id = "<%s@%s>" % (row[0], group_name)
            line_count = len(row[6].split('\n'))
            xref = 'Xref: %s %s:%s' % (settings.nntp_hostname, group_name, row[0])
            if row[1] != row[0]:
                reference = "<%s@%s>" % (row[1], group_name)
            else:
                reference = ""
            # message_number <tab> subject <tab> author <tab> date <tab> message_id <tab> reference <tab> bytes <tab> lines <tab> xref
            overviews.append("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (row[0], row[4], author, formatted_time, message_id, reference, len(strutil.format_body(row[6])), line_count, xref))
        return "\r\n".join(overviews)

    def get_XPAT(self, group_name, header, pattern, start_id, end_id='ggg'):
        # XXX: need to actually check for the header values being passed as
        # XXX: not all header names map to column names on the tables
        forum_id = self.get_forum(group_name)
        prefix = settings.phpbb_table_prefix
        stmt = """
                SELECT
                    A.post_id,
                    A.topic_id,
                    C.username,
                    C.user_email,
                    B.post_subject,
                    A.post_time,
                    B.post_text,
                    A.post_username
                FROM
                    %sposts A, 
                    %sposts_text B
                LEFT JOIN
                    %susers C
                ON
                    A.poster_id=C.user_id
                WHERE
                    A.forum_id=%s AND
                    %s REGEXP '%s' AND
                    A.post_id = B.post_id AND
                    A.post_id >= %s""" % (prefix, prefix, prefix, forum_id, header, strutil.format_wildcards(pattern), start_id)
        if end_id != 'ggg':
            stmt = "%s AND A.post_id <= %s" % (stmt, end_id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        result = list(self.cursor.fetchall())
        hdrs = []
        for row in result:
            if header.upper() == 'SUBJECT':
                hdrs.append('%s %s' % (row[0], row[4]))
            elif header.upper() == 'FROM':
                # XXX: totally broken with empty values for the email address
                hdrs.append('%s %s <%s>' % (row[0], row[2], row[3]))
            elif header.upper() == 'DATE':
                hdrs.append('%s %s' % (row[0], strutil.get_formatted_time(time.localtime(result[5]))))
            elif header.upper() == 'MESSAGE-ID':
                hdrs.append('%s <%s@%s>' % (row[0], row[0], group_name))
            elif (header.upper() == 'REFERENCES') and (row[1] != 0):
                hdrs.append('%s <%s@%s>' % (row[0], row[1], group_name))
            elif header.upper() == 'BYTES':
                hdrs.append('%s %s' % (row[0], len(row[6])))
            elif header.upper() == 'LINES':
                hdrs.append('%s %s' % (row[0], len(row[6].split('\n'))))
            elif header.upper() == 'XREF':
                hdrs.append('%s %s %s:%s' % (row[0], settings.nntp_hostname, group_name, row[0]))
        if len(hdrs) == 0:
            return ""
        else:
            return "\r\n".join(hdrs)

    def get_LISTGROUP(self, group_name):
        forum_id = self.get_forum(group_name)
        stmt = """
                SELECT
                    post_id
                FROM
                    %sposts
                WHERE
                    forum_id=%s
                ORDER BY
                    post_id ASC""" % (settings.phpbb_table_prefix, forum_id)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        return "\r\n".join(["%s" % k for k in result])

    def get_XGTITLE(self, pattern=None):
        stmt = """
                SELECT
                    nntp_group_name,
                    forum_desc
                FROM
                    %sforums
                WHERE
                    LENGTH(nntp_group_name) > 0""" % (settings.phpbb_table_prefix)
        if pattern != None:
            stmt = stmt + """ AND
                    nntp_group_name REGEXP '%s'""" % (strutil.format_wildcards(pattern))
        stmt = stmt + """
                ORDER BY
                    nntp_group_name ASC"""
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        return "\r\n".join(["%s %s" % (k, v) for k, v in result])

    def get_XHDR(self, group_name, header, style, range):
        forum_id = self.get_forum(group_name)
        prefix = settings.phpbb_table_prefix
        stmt = """
                SELECT
                    A.post_id,
                    A.topic_id,
                    C.username,
                    C.user_email,
                    B.post_subject,
                    A.post_time,
                    B.post_text,
                    A.post_username
                FROM
                    %sposts A,
                    %sposts_text B
                LEFT JOIN
                    %susers C
                ON
                    A.poster_id=C.user_id
                WHERE
                    A.forum_id=%s AND
                    A.post_id = B.post_id AND """ % (prefix, prefix, prefix, forum_id)
        if style == 'range':
            stmt = '%s A.post_id >= %s' % (stmt, range[0])
            if len(range) == 2:
                stmt = '%s AND A.post_id <= %s' % (stmt, range[1])
        else:
            stmt = '%s A.id = %s' % (stmt, range[0])
        if self.cursor.execute(stmt) == 0:
            return None
        result = self.cursor.fetchall()
        hdrs = []
        for row in result:
            if header.upper() == 'SUBJECT':
                hdrs.append('%s %s' % (row[0], row[4]))
            elif header.upper() == 'FROM':
                hdrs.append('%s %s <%s>' % (row[0], row[2], row[3]))
            elif header.upper() == 'DATE':
                hdrs.append('%s %s' % (row[0], strutil.get_formatted_time(time.localtime(result[5]))))
            elif header.upper() == 'MESSAGE-ID':
                hdrs.append('%s <%s@%s>' % (row[0], row[0], group_name))
            elif (header.upper() == 'REFERENCES') and (row[1] != 0):
                hdrs.append('%s <%s@%s>' % (row[0], row[1], group_name))
            elif header.upper() == 'BYTES':
                hdrs.append('%s %s' % (row[0], len(row[6])))
            elif header.upper() == 'LINES':
                hdrs.append('%s %s' % (row[0], len(row[6].split('\n'))))
            elif header.upper() == 'XREF':
                hdrs.append('%s %s %s:%s' % (row[0], settings.nntp_hostname, group_name, row[0]))
        if len(hdrs) == 0:
            return ""
        else:
            return "\r\n".join(hdrs)

    def do_POST(self, group_name, lines, ip_address, username=''):
        forum_id = self.get_forum(group_name)
        prefix = settings.phpbb_table_prefix
        body = self.get_message_body(lines)
        author, email = from_regexp.search(lines, 0).groups()
        subject = subject_regexp.search(lines, 0).groups()[0].strip()
        # get the authentication information now
        if username != '':
            stmt = """
                    SELECT
                        user_id
                    FROM
                        %susers
                    WHERE
                        username='%s'""" % (prefix, username)
            num_rows = self.cursor.execute(stmt)
            if num_rows == 0:
                poster_id = -1
            else:
                poster_id = self.cursor.fetchone()[0]
            post_username = ''
        else:
            poster_id = -1
            post_username = author
        if lines.find('References') != -1:
            # get the 'modifystamp' value from the parent (if any)
            references = references_regexp.search(lines, 1).groups()
            parent_id, void = references[-1].strip().split('@')
            stmt = """
                    SELECT
                        topic_id
                    FROM
                        %sposts
                    WHERE
                        post_id=%s
                    GROUP BY
                        post_id""" % (prefix, parent_id)
            num_rows = self.cursor.execute(stmt)
            if num_rows == 0:
                return None
            thread_id = self.cursor.fetchone()[0]
        else:
            # create a new topic
            stmt = """
                    INSERT INTO
                        %stopics
                    (
                        forum_id,
                        topic_title,
                        topic_poster,
                        topic_time,
                        topic_status,
                        topic_vote,
                        topic_type
                    ) VALUES (
                        %s,
                        '%s',
                        %s,
                        UNIX_TIMESTAMP(),
                        0,
                        0,
                        0
                    )""" % (prefix, forum_id, self.quote_string(subject), poster_id)
            self.cursor.execute(stmt)
            thread_id = self.cursor.insert_id()
        stmt = """
                INSERT INTO
                    %sposts
                (
                    topic_id,
                    forum_id,
                    poster_id,
                    post_time,
                    poster_ip,
                    post_username,
                    enable_bbcode,
                    enable_html,
                    enable_smilies,
                    enable_sig
                ) VALUES (
                    %s,
                    %s,
                    %s,
                    UNIX_TIMESTAMP(),
                    '%s',
                    '%s',
                    1,
                    0,
                    1,
                    0
                )""" % (prefix, thread_id, forum_id, poster_id, self.encode_ip(ip_address), post_username)
        self.cursor.execute(stmt)
        new_id = self.cursor.insert_id()
        if not new_id:
            return None
        else:
            # insert into the '*posts_text' table
            stmt = """
                    INSERT INTO
                        %sposts_text
                    (
                        post_id,
                        bbcode_uid,
                        post_subject,
                        post_text
                    ) VALUES (
                        %s,
                        '%s',
                        '%s',
                        '%s'
                    )""" % (prefix, new_id, self.make_bbcode_uid(), self.quote_string(subject), self.quote_string(body))
            if not self.cursor.execute(stmt):
                # delete from 'topics' and 'posts' tables before returning...
                stmt = """
                        DELETE FROM
                            %stopics
                        WHERE
                            topic_id=%s""" % (prefix, thread_id)
                self.cursor.execute(stmt)
                stmt = """
                        DELETE FROM
                            %sposts
                        WHERE
                            post_id=%s""" % (prefix, new_id)
                self.cursor.execute(stmt)
                return None
            else:
                # setup last post on the topic thread (Patricio Anguita <pda@ing.puc.cl>)
                stmt = """
                        UPDATE
                            %stopics
                        SET
                            topic_last_post_id = %s
                        WHERE
                            topic_id=%s""" % (prefix, new_id, thread_id)
                self.cursor.execute(stmt)
                # if this is the first post on the thread.. (Patricio Anguita <pda@ing.puc.cl>)
                if lines.find('References') == -1:
                    stmt = """
                            UPDATE
                                %stopics
                            SET
                                topic_first_post_id=%s
                            WHERE
                                topic_id=%s AND
                                topic_first_post_id=0""" % (prefix, new_id, thread_id)
                    self.cursor.execute(stmt)
                return 1
