#!/usr/bin/env python
# $Id: portable_locker.py,v 1.2 2002-10-03 01:05:24 jpm Exp $

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

    def lock(fd, flags):
        hfile = win32file._get_osfhandle(fd.fileno(  ))
        win32file.LockFileEx(hfile, flags, 0, 0xffff0000, __overlapped)

    def unlock(fd):
        hfile = win32file._get_osfhandle(fd.fileno(  ))
        win32file.UnlockFileEx(hfile, 0, 0xffff0000, __overlapped)

elif os.name == 'posix':
    import fcntl
    LOCK_EX = fcntl.LOCK_EX
    LOCK_SH = fcntl.LOCK_SH
    LOCK_NB = fcntl.LOCK_NB

    def lock(fd, flags):
        fcntl.flock(fd.fileno(), flags)

    def unlock(fd):
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)

else:
    raise RuntimeError("portable_locker only defined for nt and posix platforms")

