#!/usr/bin/env python
# Copyright (c) 2001 Joao Prado Maia. See the LICENSE file for more information.
# $Id: settings.py,v 1.1 2002-01-10 16:21:00 jpm Exp $
import time

log_path = "/home/jpm/papercut/logs/"
log_file = log_path + "papercut.log"
hostname = 'phpbrasil.com'
backend_type = "mysql"
dbname = "phpbrasil_dev"
dbuser = "anonimo"
dbpass = "anonimo"

def logEvent(msg):
    f = open(log_file, "a")
    f.write("[%s] %s\n" % (time.strftime("%a %b %d %H:%M:%S %Y", time.gmtime()), msg))
    f.close()
