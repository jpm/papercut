#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: settings.py,v 1.5 2002-01-16 23:11:45 jpm Exp $
import time

log_path = "/home/jpm/papercut/logs/"
log_file = log_path + "papercut.log"
hostname = 'phpbrasil.com'
backend_type = "phorum_mysql"
dbname = "phpbrasil_dev"
dbuser = "anonimo"
dbpass = "anonimo"

def logEvent(msg):
    f = open(log_file, "a")
    f.write("[%s] %s\n" % (time.strftime("%a %b %d %H:%M:%S %Y", time.gmtime()), msg))
    f.close()
