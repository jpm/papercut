#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: settings.py,v 1.12 2002-04-12 04:41:05 jpm Exp $
import time
import sys
import os

#
# The following configuration settings should be pretty self-explanatory, but
# please let me know if this is not complete or if more information / examples
# are needed.
#

# full path for where Papercut will store the log file
log_path = "/home/papercut/logs/"
# the actual log filename
log_file = log_path + "papercut.log"

# hostname that Papercut will bind against
nntp_hostname = 'nntp.domain.com'
# usually 119, but use 563 for an SSL server
nntp_port = 119
# server runs as an SSL server ? ('yes' or 'no)
nntp_ssl = 'no'
# if it is an SSL server, complete the following two variables
ssl_cert_path = ''
ssl_key_path = ''

# check for the appropriate path
if nntp_ssl == 'yes' and (ssl_cert_path == '' or ssl_key_path == '' or not os.path.exists(ssl_cert_path) or not os.path.exists(ssl_key_path)):
    sys.exit("Please configure the 'ssl_cert_path' and 'ssl_key_path' options correctly")

# server needs authentication ? ('yes' or 'no')
nntp_auth = 'no'
# backend that Papercut will use to authenticate the users
auth_backend = ''

# check for the appropriate options
if nntp_auth == 'yes' and auth_backend == '':
    sys.exit("Please configure the 'nntp_auth' and 'auth_backend' options correctly")

# type of server ('read-only' or 'read-write')
server_type = 'read-write'

# backend that Papercut will use to get the actual articles content
storage_backend = "phorum_mysql"

# for the forwarding_proxy backend, set the next option to the remote nntp server
forward_host = 'news.php.net'

# full path to the directory where the Phorum configuration files are stored
phorum_settings_path = "/home/jpm/www/domain.com/phorum_settings/"

# the version for the installed copy of Phorum
phorum_version = "3.3.2a"

# check for the trailing slash
if phorum_settings_path[-1] != '/':
    phorum_settings_path = phorum_settings_path + '/'

# configuration values for 'backends/phorum_mysql.py'
# database connection variables
dbhost = "localhost"
dbname = "phorum"
dbuser = "anonymous"
dbpass = "anonymous"

# helper function to log information
def logEvent(msg):
    f = open(log_file, "a")
    f.write("[%s] %s\n" % (time.strftime("%a %b %d %H:%M:%S %Y", time.gmtime()), msg))
    f.close()
