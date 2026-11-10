#!/usr/bin/env python3
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: phpbb_mysql_users.py,v 1.4 2003-09-19 03:11:51 jpm Exp $
import MySQLdb
import settings
import hashlib

class Papercut_Auth:
    """
    Authentication backend interface for the phpBB web message board software (http://www.phpbb.com)
    
    This backend module tries to authenticate the users against the phpbb_users table.
    
    Many thanks to Chip McClure <vhm3 AT gigguardian.com> for the work on this file.
    """

    def __init__(self):
        self.conn = MySQLdb.connect(host=settings.dbhost, db=settings.dbname, user=settings.dbuser, passwd=settings.dbpass)
        self.cursor = self.conn.cursor()

    def is_valid_user(self, username, password):
        stmt = """
                SELECT
                    user_password
                FROM
                    %susers
                WHERE
                    username=%%s
                """ % (settings.phpbb_table_prefix)
        num_rows = self.cursor.execute(stmt, (username,))
        if num_rows == 0 or num_rows is None:
            settings.logEvent('Error - Authentication failed for username \'%s\' (user not found)' % (username))
            return 0
        db_password = self.cursor.fetchone()[0]
        if db_password != hashlib.md5(password.encode('utf-8')).hexdigest():
            settings.logEvent('Error - Authentication failed for username \'%s\' (incorrect password)' % (username))
            return 0
        else:
            return 1

