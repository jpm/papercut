#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: settings.py,v 1.8 2002-03-24 18:48:50 jpm Exp $
import time

#
# The following configuration settings should be pretty self-explanatory, but
# please let me know if this is not complete or if more information / examples
# are needed.
#

# full path for where Papercut will store the log file
log_path = "/home/jpm/papercut/logs/"
# the actual log filename
log_file = log_path + "papercut.log"

# hostname that Papercut will bind against
nntp_hostname = 'nntp.domain.com'
nntp_port = 119

# type of server ('read-only' or 'read-write')
server_type = 'read-write'

# backend that Papercut will use to get the actual articles content
backend_type = "phorum_mysql"

# full path to the directory where the Phorum configuration files are stored
phorum_settings_path = "/home/jpm/www/phpbrasil.com/phorum_settings/"

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
