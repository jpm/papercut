#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: phorum_pgsql_users.py,v 1.3 2004-01-14 22:26:40 jpm Exp $
from pyPgSQL import PgSQL
import settings
import crypt
import md5

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
        num_rows = self.cursor.execute(stmt)
        if num_rows == 0 or num_rows is None:
            settings.logEvent('Error - Authentication failed for username \'%s\' (user not found)' % (username))
            return 0
        db_password = self.cursor.fetchone()[0]
        # somehow detect the version of phorum being used and guess the encryption type
        if len(db_password) == 32:
            result = (db_password != md5.new(password).hexdigest())
        else:
            result = (db_password != crypt.crypt(password, password[:settings.PHP_CRYPT_SALT_LENGTH]))
        if result:
            settings.logEvent('Error - Authentication failed for username \'%s\' (incorrect password)' % (username))
            return 0
        else:
            return 1
