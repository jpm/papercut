#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: postnuke_phpbb_mysql_users.py,v 1.1 2004-08-01 01:51:48 jpm Exp $
import MySQLdb
import settings
import md5

class Papercut_Auth:
    """
    Authentication backend interface for the phpBB web message board software (http://www.phpbb.com) when used inside PostNuke.
    
    This backend module tries to authenticate the users against the phpbb_users table.
    """

    def __init__(self):
        self.conn = MySQLdb.connect(host=settings.dbhost, db=settings.dbname, user=settings.dbuser, passwd=settings.dbpass)
        self.cursor = self.conn.cursor()

    def is_valid_user(self, username, password):
        stmt = """
                SELECT
                    pn_pass
                FROM
                    nuke_users
                WHERE
                    pn_uname='%s'
                """ % (username)
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

