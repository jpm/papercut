#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: phorum_pgsql_users.py,v 1.1 2003-04-26 00:22:12 jpm Exp $
from pyPgSQL import PgSQL
import settings
import crypt

class Papercut_Auth:
    """
    Authentication backend interface for the Phorum web message board software (http://phorum.org)
    
    This backend module tries to authenticate the users against the forums_auth table, which is
    used by Phorum to save its user based information, be it with a moderator level or not.
    """

    def __init__(self):
        self.conn = PgSQL.connect(database=settings.dbname, user=settings.dbuser)
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
        print "sql ->", stmt
        num_rows = self.cursor.execute(stmt)
        print "num_rows ->", num_rows
        if num_rows == 0 or num_rows is None:
            settings.logEvent('Error - Authentication failed for username \'%s\' (user not found)' % (username))
            return 0
        print "result ->", self.cursor.fetchone()
        db_password = self.cursor.fetchone()[0]
        if db_password != crypt.crypt(password, password[:settings.PHP_CRYPT_SALT_LENGTH]):
            settings.logEvent('Error - Authentication failed for username \'%s\' (incorrect password)' % (username))
            return 0
        else:
            return 1
