#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: phorum_pgsql.py,v 1.11 2004-02-01 05:23:13 jpm Exp $
from pyPgSQL import PgSQL
import time
from mimify import mime_encode_header, mime_decode_header
import re
import settings
import mime
import strutil
import smtplib
import md5

# patch by Andreas Wegmann <Andreas.Wegmann@VSA.de> to fix the handling of unusual encodings of messages
q_quote_multiline = re.compile("=\?(.*?)\?[qQ]\?(.*?)\?=.*?=\?\\1\?[qQ]\?(.*?)\?=", re.M | re.S)

# we don't need to compile the regexps everytime..
doubleline_regexp = re.compile("^\.\.", re.M)
singleline_regexp = re.compile("^\.", re.M)
from_regexp = re.compile("^From:(.*)<(.*)>", re.M)
subject_regexp = re.compile("^Subject:(.*)", re.M)
references_regexp = re.compile("^References:(.*)<(.*)>", re.M)
lines_regexp = re.compile("^Lines:(.*)", re.M)
# phorum configuration files related regexps
moderator_regexp = re.compile("(.*)PHORUM\['ForumModeration'\](.*)='(.*)';", re.M)
url_regexp = re.compile("(.*)PHORUM\['forum_url'\](.*)='(.*)';", re.M)
admin_regexp = re.compile("(.*)PHORUM\['admin_url'\](.*)='(.*)';", re.M)
server_regexp = re.compile("(.*)PHORUM\['forum_url'\](.*)='(.*)http://(.*)/(.*)';", re.M)
mail_code_regexp = re.compile("(.*)PHORUM\['PhorumMailCode'\](.*)=(.*)'(.*)';", re.M)

class Papercut_Storage:
    """
    Storage Backend interface for the Phorum web message board software (http://phorum.org)
    
    This is the interface for Phorum running on a PostgreSQL database. For more information
    on the structure of the 'storage' package, please refer to the __init__.py
    available on the 'storage' sub-directory.
    """

    def __init__(self):
        self.conn = PgSQL.connect(host=settings.dbhost, database=settings.dbname, user=settings.dbuser, password=settings.dbpass)
        self.cursor = self.conn.cursor()

    def get_message_body(self, headers):
        """Parses and returns the most appropriate message body possible.
        
        The function tries to extract the plaintext version of a MIME based
        message, and if it is not available then it returns the html version.        
        """
        return mime.get_text_message(headers)

    def group_exists(self, group_name):
        stmt = """
                SELECT
                    COUNT(*) AS total
                FROM
                    forums
                WHERE
                    LOWER(nntp_group_name)=LOWER('%s')""" % (group_name)
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def article_exists(self, group_name, style, range):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    COUNT(*) AS total
                FROM
                    %s
                WHERE
                    approved='Y'""" % (table_name)
        if style == 'range':
            stmt = "%s AND id > %s" % (stmt, range[0])
            if len(range) == 2:
                stmt = "%s AND id < %s" % (stmt, range[1])
        else:
            stmt = "%s AND id = %s" % (stmt, range[0])
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def get_first_article(self, group_name):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    MIN(id) AS first_article
                FROM
                    %s
                WHERE
                    approved='Y'""" % (table_name)
        self.cursor.execute(stmt)
        minimum = self.cursor.fetchone()[0]
        if minimum is None:
            return 0
        else:
            return minimum

    def get_group_stats(self, group_name):
        total, max, min = self.get_table_stats(self.get_table_name(group_name))
        return (total, min, max, group_name)

    def get_table_stats(self, table_name):
        stmt = """
                SELECT
                   COUNT(id) AS total,
                   MAX(id) AS maximum,
                   MIN(id) AS minimum
                FROM
                    %s
                WHERE
                    approved='Y'""" % (table_name)
        self.cursor.execute(stmt)
        total, maximum, minimum = self.cursor.fetchone()
        if maximum is None:
            maximum = 0
        if minimum is None:
            minimum = 0
        return (total, maximum, minimum)

    def get_table_name(self, group_name):
        stmt = """
                SELECT
                    table_name
                FROM
                    forums
                WHERE
                    nntp_group_name LIKE '%s'""" % (group_name.replace('*', '%'))
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

    def get_message_id(self, msg_num, group):
        return '<%s@%s>' % (msg_num, group)

    def get_notification_emails(self, forum_id):
        # open the configuration file
        fp = open("%s%s.php" % (settings.phorum_settings_path, forum_id), "r")
        content = fp.read()
        fp.close()
        # get the value of the configuration variable
        recipients = []
        mod_code = moderator_regexp.search(content, 0).groups()
        if mod_code[2] == 'r' or mod_code[2] == 'a':
            # get the moderator emails from the forum_auth table
            stmt = """
                    SELECT
                        email
                    FROM
                        forums_auth,
                        forums_moderators
                    WHERE
                        user_id=id AND
                        forum_id=%s""" % (forum_id)
            self.cursor.execute(stmt)
            result = list(self.cursor.fetchall())
            for row in result:
                recipients.append(row[0].strip())
        return recipients

    def send_notifications(self, group_name, msg_id, thread_id, parent_id, msg_author, msg_email, msg_subject, msg_body):
        msg_tpl = """From: Phorum <%(recipient)s>
To: %(recipient)s
Subject: Moderate for %(forum_name)s at %(phorum_server_hostname)s Message: %(msg_id)s.

Subject: %(msg_subject)s
Author: %(msg_author)s
Message: %(phorum_url)s/read.php?f=%(forum_id)s&i=%(msg_id)s&t=%(thread_id)s&admview=1

%(msg_body)s

To delete this message use this URL:
%(phorum_admin_url)s?page=easyadmin&action=del&type=quick&id=%(msg_id)s&num=1&thread=%(thread_id)s

To edit this message use this URL:
%(phorum_admin_url)s?page=edit&srcpage=easyadmin&id=%(msg_id)s&num=1&mythread=%(thread_id)s

"""
        # get the forum_id for this group_name
        stmt = """
                SELECT
                    id,
                    name
                FROM
                    forums
                WHERE
                    nntp_group_name='%s'""" % (group_name)
        self.cursor.execute(stmt)
        forum_id, forum_name = self.cursor.fetchone()
        forum_name.strip()
        # open the main configuration file
        fp = open("%sforums.php" % (settings.phorum_settings_path), "r")
        content = fp.read()
        fp.close()
        # regexps to get the content from the phorum configuration files
        phorum_url = url_regexp.search(content, 0).groups()[2]
        phorum_admin_url = admin_regexp.search(content, 0).groups()[2]
        phorum_server_hostname = server_regexp.search(content, 0).groups()[3]
        # connect to the SMTP server
        smtp = smtplib.SMTP('localhost')
        emails = self.get_notification_emails(forum_id)
        for recipient in emails:
            current_msg = msg_tpl % vars()
            smtp.sendmail("Phorum <%s>" % (recipient), recipient, current_msg)

        # XXX: Coding blind here. I really don't know much about how Phorum works with
        # XXX: sending forum postings as emails, but it's here. Let's call this a
        # XXX: temporary implementation. Should work fine, I guess.
        phorum_mail_code = mail_code_regexp.search(content, 0).groups()[3]
        notification_mail_tpl = """Message-ID: <%(random_msgid)s@%(phorum_server_hostname)s>
From: %(msg_author)s %(msg_email)s
Subject: %(msg_subject)s
To: %(forum_name)s <%(email_list)s>
Return-Path: <%(email_return)s>
Reply-To: %(email_return)s
X-Phorum-%(phorum_mail_code)s-Version: Phorum %(phorum_version)s
X-Phorum-%(phorum_mail_code)s-Forum: %(forum_name)s
X-Phorum-%(phorum_mail_code)s-Thread: %(thread_id)s
X-Phorum-%(phorum_mail_code)s-Parent: %(parent_id)s

This message was sent from: %(forum_name)s.
<%(phorum_url)s/read.php?f=%(forum_id)s&i=%(msg_id)s&t=%(thread_id)s>
----------------------------------------------------------------

%(msg_body)s

----------------------------------------------------------------
Sent using Papercut version %(__VERSION__)s <http://papercut.org>
"""
        stmt = """
                SELECT
                    email_list,
                    email_return
                FROM
                    forums
                WHERE
                    LENGTH(email_list) > 0 AND
                    id=%s""" % (forum_id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 1:
            email_list, email_return = self.cursor.fetchone()
            msg_body = strutil.wrap(msg_body)
            if len(msg_email) > 0:
                msg_email = '<%s>' % msg_email
            else:
                msg_email = ''
            random_msgid = md5.new(str(time.clock())).hexdigest()
            # this is pretty ugly, right ?
            from papercut import __VERSION__
            phorum_version = settings.phorum_version
            current_msg = notification_mail_tpl % vars()
            smtp.sendmail('%s %s' % (msg_author, msg_email), email_list, current_msg)
        smtp.quit()

    def get_NEWGROUPS(self, ts, group='%'):
        stmt = """
                SELECT
                    nntp_group_name
                FROM
                    forums
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
                    forums
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
                        %s
                    WHERE
                        approved='Y' AND
                        DATE_PART('epoch', datestamp) >= %s""" % (table, ts)
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
                    nntp_group_name,
                    table_name
                FROM
                    forums
                WHERE
                    LENGTH(nntp_group_name) > 0
                ORDER BY
                    nntp_group_name ASC"""
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
                    approved='Y' AND
                    id=%s""" % (table_name, id)
        return self.cursor.execute(stmt)

    def get_ARTICLE(self, group_name, id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    A.id,
                    author,
                    email,
                    subject,
                    DATE_PART('epoch', datestamp) AS datestamp,
                    body,
                    parent
                FROM
                    %s A,
                    %s_bodies B
                WHERE
                    A.approved='Y' AND
                    A.id=B.id AND
                    A.id=%s""" % (table_name, table_name, id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        result = list(self.cursor.fetchone())
        if len(result[2]) == 0:
            author = result[1].strip()
        else:
            author = "%s <%s>" % (result[1].strip(), result[2].strip())
        formatted_time = strutil.get_formatted_time(time.localtime(result[4]))
        headers = []
        headers.append("Path: %s" % (settings.nntp_hostname))
        headers.append("From: %s" % (author))
        headers.append("Newsgroups: %s" % (group_name))
        headers.append("Date: %s" % (formatted_time))
        headers.append("Subject: %s" % (result[3].strip()))
        headers.append("Message-ID: <%s@%s>" % (result[0], group_name))
        headers.append("Xref: %s %s:%s" % (settings.nntp_hostname, group_name, result[0]))
        if result[6] != 0:
            headers.append("References: <%s@%s>" % (result[6], group_name))
        return ("\r\n".join(headers), strutil.format_body(result[5]))

    def get_LAST(self, group_name, current_id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id
                FROM
                    %s
                WHERE
                    approved='Y' AND
                    id < %s
                ORDER BY
                    id DESC
                LIMIT 1, 0""" % (table_name, current_id)
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
                    approved='Y' AND
                    id > %s
                ORDER BY
                    id ASC
                LIMIT 1, 0""" % (table_name, current_id)
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
                    email,
                    subject,
                    DATE_PART('epoch', datestamp) AS datestamp,
                    parent
                FROM
                    %s
                WHERE
                    approved='Y' AND
                    id=%s""" % (table_name, id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        result = list(self.cursor.fetchone())
        if len(result[2]) == 0:
            author = result[1].strip()
        else:
            author = "%s <%s>" % (result[1].strip(), result[2].strip())
        formatted_time = strutil.get_formatted_time(time.localtime(result[4]))
        headers = []
        headers.append("Path: %s" % (settings.nntp_hostname))
        headers.append("From: %s" % (author))
        headers.append("Newsgroups: %s" % (group_name))
        headers.append("Date: %s" % (formatted_time))
        headers.append("Subject: %s" % (result[3].strip()))
        headers.append("Message-ID: <%s@%s>" % (result[0], group_name))
        headers.append("Xref: %s %s:%s" % (settings.nntp_hostname, group_name, result[0]))
        if result[5] != 0:
            headers.append("References: <%s@%s>" % (result[5], group_name))
        return "\r\n".join(headers)

    def get_BODY(self, group_name, id):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    B.body
                FROM
                    %s A,
                    %s_bodies B
                WHERE
                    A.id=B.id AND
                    A.approved='Y' AND
                    B.id=%s""" % (table_name, table_name, id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        else:
            return strutil.format_body(self.cursor.fetchone()[0])

    def get_XOVER(self, group_name, start_id, end_id='ggg'):
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    A.id,
                    parent,
                    author,
                    email,
                    subject,
                    DATE_PART('epoch', datestamp) AS datestamp,
                    B.body
                FROM
                    %s A, 
                    %s_bodies B
                WHERE
                    A.approved='Y' AND
                    A.id=B.id AND
                    A.id >= %s""" % (table_name, table_name, start_id)
        if end_id != 'ggg':
            stmt = "%s AND A.id <= %s" % (stmt, end_id)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        overviews = []
        for row in result:
            if row[3] == '':
                author = row[2].strip()
            else:
                author = "%s <%s>" % (row[2].strip(), row[3].strip())
            formatted_time = strutil.get_formatted_time(time.localtime(row[5]))
            message_id = "<%s@%s>" % (row[0], group_name)
            line_count = len(row[6].split('\n'))
            xref = 'Xref: %s %s:%s' % (settings.nntp_hostname, group_name, row[0])
            if row[1] != 0:
                reference = "<%s@%s>" % (row[1], group_name)
            else:
                reference = ""
            # message_number <tab> subject <tab> author <tab> date <tab> message_id <tab> reference <tab> bytes <tab> lines <tab> xref
            overviews.append("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (row[0], row[4].strip(), author, formatted_time, message_id, reference, len(strutil.format_body(row[6])), line_count, xref))
        return "\r\n".join(overviews)

    def get_XPAT(self, group_name, header, pattern, start_id, end_id='ggg'):
        # XXX: need to actually check for the header values being passed as
        # XXX: not all header names map to column names on the tables
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    A.id,
                    parent,
                    author,
                    email,
                    subject,
                    DATE_PART('epoch', datestamp) AS datestamp,
                    B.body
                FROM
                    %s A, 
                    %s_bodies B
                WHERE
                    A.approved='Y' AND
                    %s LIKE '%s' AND
                    A.id = B.id AND
                    A.id >= %s""" % (table_name, table_name, header, strutil.format_wildcards_sql(pattern), start_id)
        if end_id != 'ggg':
            stmt = "%s AND A.id <= %s" % (stmt, end_id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        result = list(self.cursor.fetchall())
        hdrs = []
        for row in result:
            if header.upper() == 'SUBJECT':
                hdrs.append('%s %s' % (row[0], row[4].strip()))
            elif header.upper() == 'FROM':
                # XXX: totally broken with empty values for the email address
                hdrs.append('%s %s <%s>' % (row[0], row[2].strip(), row[3].strip()))
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
        table_name = self.get_table_name(group_name)
        stmt = """
                SELECT
                    id
                FROM
                    %s
                WHERE
                    approved='Y'
                ORDER BY
                    id ASC""" % (table_name)
        self.cursor.execute(stmt)
        result = list(self.cursor.fetchall())
        return "\r\n".join(["%s" % k for k in result])

    def get_XGTITLE(self, pattern=None):
        stmt = """
                SELECT
                    nntp_group_name,
                    description
                FROM
                    forums
                WHERE
                    LENGTH(nntp_group_name) > 0"""
        if pattern != None:
            stmt = stmt + """ AND
                    nntp_group_name LIKE '%s'""" % (strutil.format_wildcards_sql(pattern))
        stmt = stmt + """
                ORDER BY
                    nntp_group_name ASC"""
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
                    DATE_PART('epoch', datestamp) AS datestamp,
                    B.body
                FROM
                    %s A,
                    %s_bodies B
                WHERE
                    A.approved='Y' AND
                    A.id = B.id AND """ % (table_name, table_name)
        if style == 'range':
            stmt = '%s A.id >= %s' % (stmt, range[0])
            if len(range) == 2:
                stmt = '%s AND A.id <= %s' % (stmt, range[1])
        else:
            stmt = '%s A.id = %s' % (stmt, range[0])
        if self.cursor.execute(stmt) == 0:
            return None
        result = self.cursor.fetchall()
        hdrs = []
        for row in result:
            if header.upper() == 'SUBJECT':
                hdrs.append('%s %s' % (row[0], row[4].strip()))
            elif header.upper() == 'FROM':
                hdrs.append('%s %s <%s>' % (row[0], row[2].strip(), row[3].strip()))
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
        table_name = self.get_table_name(group_name)
        body = self.get_message_body(lines)
        author, email = from_regexp.search(lines, 0).groups()
        subject = subject_regexp.search(lines, 0).groups()[0].strip()
        # patch by Andreas Wegmann <Andreas.Wegmann@VSA.de> to fix the handling of unusual encodings of messages
        lines = mime_decode_header(re.sub(q_quote_multiline, "=?\\1?Q?\\2\\3?=", lines))
        if lines.find('References') != -1:
            # get the 'modifystamp' value from the parent (if any)
            references = references_regexp.search(lines, 0).groups()
            parent_id, void = references[-1].strip().split('@')
            stmt = """
                    SELECT
                        MAX(id) AS next_id
                    FROM
                        %s""" % (table_name)
            num_rows = self.cursor.execute(stmt)
            if num_rows == 0:
                new_id = 1
            else:
                new_id = self.cursor.fetchone()[0]
                if new_id is None:
                    new_id = 1
                else:
                    new_id = new_id + 1
            stmt = """
                    SELECT
                        id,
                        thread,
                        modifystamp
                    FROM
                        %s
                    WHERE
                        approved='Y' AND
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
                        MAX(id) AS next_id,
                        DATE_PART('epoch', CURRENT_TIMESTAMP())
                    FROM
                        %s""" % (table_name)
            self.cursor.execute(stmt)
            new_id, modifystamp = self.cursor.fetchone()
            if new_id is None:
                new_id = 1
            else:
                new_id = new_id + 1
            modifystamp = int(modifystamp)
            parent_id = 0
            thread_id = new_id
        stmt = """
                INSERT INTO
                    """ + table_name + """
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
                """
        if not self.cursor.execute(stmt, (new_id, thread_id, parent_id, author.strip(), subject.strip(), email.strip(), ip_address, modifystamp,)):
            return None
        else:
            # insert into the '*_bodies' table
            stmt = """
                    INSERT INTO
                        """ + table_name + """_bodies
                    (
                        id,
                        body,
                        thread
                    ) VALUES (
                        %s,
                        '%s',
                        %s
                    )"""
            if not self.cursor.execute(stmt, (new_id, body, thread_id,)):
                # delete from 'table_name' before returning..
                stmt = """
                        DELETE FROM
                            %s
                        WHERE
                            id=%s""" % (table_name, new_id)
                self.cursor.execute(stmt)
                return None
            else:
                # alert forum moderators
                self.send_notifications(group_name, new_id, thread_id, parent_id, author.strip(), email.strip(), subject.strip(), body)
                return 1
