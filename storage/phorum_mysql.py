#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: phorum_mysql.py,v 1.34 2002-04-12 04:41:05 jpm Exp $
import MySQLdb
import time
from mimify import mime_encode_header
import re
import settings
import mime
import smtplib
import binascii
import md5

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
    
    This is the interface for Phorum running on a MySQL database. For more information
    on the structure of the 'storage' package, please refer to the __init__.py
    available on the 'storage' sub-directory.
    """

    def __init__(self):
        self.conn = MySQLdb.connect(host=settings.dbhost, db=settings.dbname, user=settings.dbuser, passwd=settings.dbpass)
        self.cursor = self.conn.cursor()

    def wrap(self, text, width=78):
        """Wraps text at a specified width.
        
        This is used on the PhorumMail feature, as to emulate completely the
        current Phorum behavior when it sends out copies of the posted
        articles.
        """
        i = 0
        while i < len(text):
            if i + width + 1 > len(text):
                i = len(text)
            else:
                findnl = text.find('\n', i)
                findspc = text.rfind(' ', i, i+width+1)
                if findspc != -1:
                    if findnl != -1 and findnl < findspc:
                        i = findnl + 1
                    else:
                        text = text[:findspc] + '\n' + text[findspc+1:]
                        i = findspc + 1
                else:
                    findspc = text.find(' ', i)
                    if findspc != -1:
                        text = text[:findspc] + '\n' + text[findspc+1:]
                        i = findspc + 1
        return text

    def get_message_body(self, headers):
        """Parses and returns the most appropriate message body possible.
        
        The function tries to extract the plaintext version of a MIME based
        message, and if it is not available then it returns the html version.        
        """
        return mime.get_text_message(headers)

    def get_formatted_time(self, time_tuple):
        """Formats the time tuple in a NNTP friendly way.
        
        Some newsreaders didn't like the date format being sent using leading
        zeros on the days, so we needed to hack our own little format.
        """
        # days without leading zeros, please
        day = int(time.strftime('%d', time_tuple))
        tmp1 = time.strftime('%a,', time_tuple)
        tmp2 = time.strftime('%b %Y %H:%M:%S %Z', time_tuple)
        return "%s %s %s" % (tmp1, day, tmp2)

    def format_body(self, text):
        """Formats the body of message being sent to the client.
        
        Since the NNTP protocol uses a single dot on a line to denote the end
        of the response, we need to substitute all leading dots on the body of
        the message with two dots.
        """
        return singleline_regexp.sub("..", text)

    def quote_string(self, text):
        """Quotes strings the MySQL way."""
        return text.replace("'", "\\'")

    def format_wildcards(self, pattern):
        pattern.replace('*', '.*')
        pattern.replace('?', '.*')
        return pattern

    def group_exists(self, group_name):
        stmt = """
                SELECT
                    COUNT(*) AS check
                FROM
                    forums
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
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        else:
            return self.cursor.fetchone()[0]

    def get_group_stats(self, table_name):
        stmt = """
                SELECT
                   COUNT(id) AS total,
                   MAX(id) AS maximum,
                   MIN(id) AS minimum
                FROM
                    %s
                WHERE
                    approved='Y'""" % (table_name)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return (0, 0, 0)
        else:
            return self.cursor.fetchone()

    def get_table_name(self, group_name):
        stmt = """
                SELECT
                    table_name
                FROM
                    forums
                WHERE
                    nntp_group_name='%s'""" % (group_name.replace('*', '%'))
        self.cursor.execute(stmt)
        return self.cursor.fetchone()[0]

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
                recipients.append(row[0])
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
            msg_body = self.wrap(msg_body)
            if len(msg_email) > 0:
                msg_email = '<%s>' % msg_email
            else:
                msg_email = ''
            random_msgid = binascii.hexlify(md5.new(str(time.clock())).digest())
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
        result = self.get_group_stats(table_name)
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
            return None
        return result

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
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
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
            author = result[1]
        else:
            author = "%s <%s>" % (result[1], result[2])
        formatted_time = self.get_formatted_time(time.localtime(result[4]))
        headers = []
        headers.append("Path: %s" % (settings.nntp_hostname))
        headers.append("From: %s" % (author))
        headers.append("Newsgroups: %s" % (group_name))
        headers.append("Date: %s" % (formatted_time))
        headers.append("Subject: %s" % (result[3]))
        headers.append("Message-ID: <%s@%s>" % (result[0], group_name))
        headers.append("Xref: %s %s:%s" % (settings.nntp_hostname, group_name, result[0]))
        if result[6] != 0:
            headers.append("References: <%s@%s>" % (result[6], group_name))
        return ("\r\n".join(headers), self.format_body(result[5]))

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
                    approved='Y' AND
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
                    email,
                    subject,
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
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
            author = result[1]
        else:
            author = "%s <%s>" % (result[1], result[2])
        formatted_time = self.get_formatted_time(time.localtime(result[4]))
        headers = []
        headers.append("Path: %s" % (settings.nntp_hostname))
        headers.append("From: %s" % (author))
        headers.append("Newsgroups: %s" % (group_name))
        headers.append("Date: %s" % (formatted_time))
        headers.append("Subject: %s" % (result[3]))
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
                author = row[2]
            else:
                author = "%s <%s>" % (row[2], row[3])
            formatted_time = self.get_formatted_time(time.localtime(row[5]))
            message_id = "<%s@%s>" % (row[0], group_name)
            line_count = len(row[6].split('\n'))
            xref = 'Xref: %s %s:%s' % (settings.nntp_hostname, group_name, row[0])
            if row[1] != 0:
                reference = "<%s@%s>" % (row[1], group_name)
            else:
                reference = ""
            # message_number <tab> subject <tab> author <tab> date <tab> message_id <tab> reference <tab> bytes <tab> lines <tab> xref
            overviews.append("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (row[0], row[4], author, formatted_time, message_id, reference, len(self.format_body(row[6])), line_count, xref))
        return "\r\n".join(overviews)

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
                    %s A, 
                    %s_bodies B
                WHERE
                    A.approved='Y' AND
                    %s REGEXP '%s' AND
                    A.id = B.id AND
                    A.id >= %s""" % (table_name, table_name, header, self.format_wildcards(pattern), start_id)
        if end_id != 'ggg':
            stmt = "%s AND A.id <= %s" % (stmt, end_id)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            return None
        result = list(self.cursor.fetchall())
        hdrs = []
        for row in result:
            if header.upper() == 'SUBJECT':
                hdrs.append('%s %s' % (row[0], row[4]))
            elif header.upper() == 'FROM':
                hdrs.append('%s %s <%s>' % (row[0], row[2], row[3]))
            elif header.upper() == 'DATE':
                hdrs.append('%s %s' % (row[0], self.get_formatted_time(time.localtime(result[5]))))
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
                    nntp_group_name REGEXP '%s'""" % (self.format_wildcards(pattern))
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
                    UNIX_TIMESTAMP(datestamp) AS datestamp,
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
                hdrs.append('%s %s' % (row[0], row[4]))
            elif header.upper() == 'FROM':
                hdrs.append('%s %s <%s>' % (row[0], row[2], row[3]))
            elif header.upper() == 'DATE':
                hdrs.append('%s %s' % (row[0], self.get_formatted_time(time.localtime(result[5]))))
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

    def do_POST(self, group_name, lines, ip_address):
        table_name = self.get_table_name(group_name)
        body = self.get_message_body(lines)
        author, email = from_regexp.search(lines, 0).groups()
        subject = subject_regexp.search(lines, 0).groups()[0].strip()
        if lines.find('References') != -1:
            # get the 'modifystamp' value from the parent (if any)
            references = references_regexp.search(lines, 1).groups()
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
                        IF(MAX(id) IS NULL, 1, MAX(id)+1) AS next_id,
                        UNIX_TIMESTAMP()
                    FROM
                        %s""" % (table_name)
            self.cursor.execute(stmt)
            new_id, modifystamp = self.cursor.fetchone()
            parent_id = 0
            thread_id = new_id
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
                """ % (table_name, new_id, thread_id, parent_id, self.quote_string(author.strip()), self.quote_string(subject), self.quote_string(email), ip_address, modifystamp)
        if not self.cursor.execute(stmt):
            return None
        else:
            # insert into the '*_bodies' table
            stmt = """
                    INSERT INTO
                        %s_bodies
                    (
                        id,
                        body,
                        thread
                    ) VALUES (
                        %s,
                        '%s',
                        %s
                    )""" % (table_name, new_id, self.quote_string(body), thread_id)
            if not self.cursor.execute(stmt):
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
                self.send_notifications(group_name, new_id, thread_id, parent_id, author.strip(), email, subject, body)
                return 1
