#!/usr/bin/env python
# Copyright (c) 2002 Joao Prado Maia. See the LICENSE file for more information.
# $Id: papercut_cache.py,v 1.3 2002-10-03 00:39:57 jpm Exp $

import binascii
import md5
import time
import os
import cPickle
import portable_locker
# papercut settings file
import settings

class CallableWrapper:
    name = None
    thecallable = None

    def __init__(self, name, thecallable):
        self.name = name
        self.thecallable = thecallable

    def __call__(self, *args, **kwds):
        filename = self._get_filename(*args, **kwds)
        if os.path.exists(filename):
            # check the expiration
            expire, result = self._get_cached_result(filename)
            diff = time.time() - expire
            if diff > settings.nntp_cache_expire:
                # remove the file and run the method again
                return self._save_result(filename, *args, **kwds)
            else:
                return result
        else:
            return self._save_result(filename, *args, **kwds)
        return 

    def _get_cached_result(self, filename):
        inf = open(filename, 'rb')
        # get an exclusive lock on the file
        portable_locker.lock(inf, portable_locker.LOCK_EX)
        expire = cPickle.load(inf)
        result = cPickle.load(inf)
        # release the lock
        portable_locker.unlock(inf)
        inf.close()
        return (expire, result)

    def _save_result(self, filename, *args, **kwds):
        result = self.thecallable(*args, **kwds)
        # save the serialized result in the file
        outf = open(filename, 'w')
        # file write lock
        portable_locker.lock(outf, portable_locker.LOCK_SH)
        cPickle.dump(time.time(), outf)
        cPickle.dump(result, outf)
        # release the lock
        portable_locker.unlock(outf)
        outf.close()
        return result

    def _get_filename(self, *args, **kwds):
        arguments = '%s%s%s' % (self.name, args, kwds)
        return '%s%s' % (settings.nntp_cache_path, binascii.hexlify(md5.new(arguments).digest()))


class Cache:
    backend = None

    def __init__(self, storage_handle):
        self.backend = storage_handle.Papercut_Storage()

    def __getattr__(self, name):
        result = getattr(self.backend, name)
        if callable(result):
            result = CallableWrapper(name, result)
        return result

