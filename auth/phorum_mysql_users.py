#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: phorum_mysql_users.py,v 1.1 2002-04-05 05:33:51 jpm Exp $
import MySQLdb
import settings
import crypt

class Papercut_Auth:
    """
    Authentication backend interface for the Phorum web message board software (http://phorum.org)
    
    This backend module tries to authenticate the users against the forums_auth table, which is
    used by Phorum to save its user based information, be it with a moderator level or not.
    """

    def __init__(self):
        self.conn = MySQLdb.connect(host=settings.dbhost, db=settings.dbname, user=settings.dbuser, passwd=settings.dbpass)
        self.cursor = self.conn.cursor()

    def is_valid_user(self, username, password):
        stmt = """
                SELECT
                    password
                FROM
                    forums_auth
                WHERE
                    username='%s'
                """ % (username)
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0:
            settings.logEvent('Error - Authentication failed for username \'%s\' (user not found)' % (username))
            return 0
        db_password = self.cursor.fetchone()[0]
        if db_password != crypt.crypt(password, password[:PHP_CRYPT_SALT_LENGTH]):
            settings.logEvent('Error - Authentication failed for username \'%s\' (incorrect password)' % (username))
            return 0
        else:
            return 1
