#!/usr/bin/env python
# $Id: portable_locker.py,v 1.1 2002-10-03 00:30:54 jpm Exp $

# Note: this was originally from Python Cookbook, which was 
# probably taken from ASPN's Python Cookbook

import os

# needs win32all to work on Windows
if os.name == 'nt':
    import win32con, win32file, pywintypes
    LOCK_EX = win32con.LOCKFILE_EXCLUSIVE_LOCK
    LOCK_SH = 0 # the default
    LOCK_NB = win32con.LOCKFILE_FAIL_IMMEDIATELY
    __overlapped = pywintypes.OVERLAPPED(  )

    def lock(file, flags):
        hfile = win32file._get_osfhandle(file.fileno(  ))
        win32file.LockFileEx(hfile, flags, 0, 0xffff0000, __overlapped)

    def unlock(file):
        hfile = win32file._get_osfhandle(file.fileno(  ))
        win32file.UnlockFileEx(hfile, 0, 0xffff0000, __overlapped)

elif os.name == 'posix':
    from fcntl import LOCK_EX, LOCK_SH, LOCK_NB

    def lock(file, flags):
        fcntl.flock(file.fileno(  ), flags)

    def unlock(file):
        fcntl.flock(file.fileno(  ), fcntl.LOCK_UN)

else:
    raise RuntimeError("PortaLocker only defined for nt and posix platforms")

