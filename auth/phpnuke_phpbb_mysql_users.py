#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
import MySQLdb
import settings
import md5

class Papercut_Auth:
    """
    Authentication backend interface for the nuke port of phpBB (http://www.phpnuke.org)
    
    This backend module tries to authenticate the users against the nuke_users table.
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
                    username='%s'
                """ % (settings.nuke_table_prefix, username)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0 or num_rows is None:
            settings.logEvent('Error - Authentication failed for username \'%s\' (user not found)' % (username))
            return 0
        db_password = self.cursor.fetchone()[0]
        if db_password != md5.new(password).hexdigest():
            settings.logEvent('Error - Authentication failed for username \'%s\' (incorrect password)' % (username))
            return 0
        else:
            return 1

