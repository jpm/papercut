#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: p2p.py,v 1.1 2002-03-20 05:46:58 jpm Exp $
import settings
import anydbm

class Papercut_Backend:
    """
    Experimental Backend interface to implement the ideas brainstormed on the
    following page: http://webseitz.fluxent.com/wiki/PaperCut
    """
    def __init__(self):
        # check for the p2p directories and dbm file now
        db = anydbm.open("p2p.dbm", "c")
