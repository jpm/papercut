#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: __init__.py,v 1.4 2002-03-26 22:55:00 jpm Exp $

#
# Papercut is a pretty dumb (some people might call it smart) server, because it
# doesn't know or care where or how the Usenet articles are stored. The system
# uses the concept of 'backends' to have access to the data being served by the
# Usenet frontend.
#
# The 'Backends' of Papercut are the actual containers of the Usenet articles,
# wherever they might be stored. The initial and proof of concept backend is
# the Phorum (http://phorum.org) one, where the Usenet articles are actually 
# Phorum messages.
#
# If you want to create a new backend, please use the phorum_mysql.py file as
# a guide for the implementation. You will need a lot of reading to understand
# the NNTP protocol (i.e. how the NNTP responses should be sent back to the 
# user), so look under the 'docs' directory for the RFC documents.
#
# As a side note, Papercut is designed to be a simple as possible, so the actual
# formatting of the responses are usually done on the backend itself. This is
# for a reason - if Papercut had to format the information coming from the 
# backends unchanged, it would need to know 'too much', like the inner workings
# of the MySQLdb module on the case of the Phorum backend and so on.
#
# Instead, Papercut expects a formatted return value from most (if not all)
# methods of the backend module. This way we can abstract as much as possible
# the data format of the articles, and have the main server code as simple and
# fast as possible.
#