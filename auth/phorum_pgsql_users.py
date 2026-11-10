#!/usr/bin/env python3
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: phorum_pgsql_users.py,v 1.3 2004-01-14 22:26:40 jpm Exp $
import psycopg2
import settings
# crypt was removed from the standard library in Python 3.13;
# on newer versions install the 'standard-crypt' package
import crypt
import hashlib

class Papercut_Auth:
    """
    Authentication backend interface for the Phorum web message board software (http://phorum.org)
    
    This backend module tries to authenticate the users against the forums_auth table, which is
    used by Phorum to save its user based information, be it with a moderator level or not.
    """

    def __init__(self):
        # (this used to ignore dbhost and dbpass, so it only worked over a
        # local socket without a password)
        self.conn = psycopg2.connect(host=settings.dbhost, database=settings.dbname, user=settings.dbuser, password=settings.dbpass)
        self.conn.autocommit = True
        self.cursor = self.conn.cursor()

    def is_valid_user(self, username, password):
        stmt = """
                SELECT
                    password
                FROM
                    forums_auth
                WHERE
                    username=%s
                """
        self.cursor.execute(stmt, (username,))
        num_rows = self.cursor.rowcount
        if num_rows == 0 or num_rows is None:
            settings.logEvent('Error - Authentication failed for username \'%s\' (user not found)' % (username))
            return 0
        db_password = self.cursor.fetchone()[0]
        # somehow detect the version of phorum being used and guess the encryption type
        if len(db_password) == 32:
            result = (db_password != hashlib.md5(password.encode('utf-8')).hexdigest())
        else:
            try:
                result = (db_password != crypt.crypt(password, password[:settings.PHP_CRYPT_SALT_LENGTH]))
            except OSError:
                # glibc rejects salt characters outside [a-zA-Z0-9./]; such a
                # password can't match a DES-crypted one
                result = True
        if result:
            settings.logEvent('Error - Authentication failed for username \'%s\' (incorrect password)' % (username))
            return 0
        else:
            return 1
