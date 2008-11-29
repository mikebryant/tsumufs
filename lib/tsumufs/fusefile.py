#!/usr/bin/python2.4
#
# Copyright (C) 2008  Google, Inc. All Rights Reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

'''TsumuFS, a NFS-based caching filesystem.'''

import os
import sys
import errno
import stat
import statvfs
import time
import traceback
import syslog

import fuse
from fuse import Fuse

import tsumufs


class FuseFile(tsumufs.Debuggable):
  '''
  This class represents a file handle for FUSE. With it, we can
  implement stateful file handle management. It also helps to reduce
  some of the complexity that the FuseThread class has obtained.
  '''

  _path  = None
  _fdFlags = None
  _fdMode  = None

  def __init__(self, path, flags, mode=None):
    self._path  = path
    self._fdFlags = flags
    self._fdMode  = mode

    self._setName('FuseFile <%s> ' % self._path)

    # Install our custom exception handler so that any exceptions are
    # output to the syslog rather than to /dev/null.
    sys.excepthook = tsumufs.syslogExceptHook

    self._debug('opcode: open | flags: %s | mode: %s'
                % (flags, mode))

    tsumufs.cacheManager.fakeOpen(path, self._fdFlags, self._fdMode)

    # Rip out any O_TRUNC options after we do the initial open -- that's
    # dangerous to do in this case, because if we get multiple write calls, we
    # just pass in the _fdMode raw, which causing multiple O_TRUNC calls to the
    # underlying file, resulting in data loss. We do the same for O_CREAT, as it
    # can also cause problems later on.

    # TODO(jtg): We should make sure these actually do what we expect instead of
    # taking it on faith.
    self._fdFlags = self._fdFlags & (~os.O_EXCL)
    self._fdFlags = self._fdFlags & (~os.O_CREAT)

  def read(self, length, offset):
    self._debug('opcode: read | path: %s | len: %d | offset: %d'
                % (self._path, length, offset))

    try:
      retval = tsumufs.cacheManager.readFile(self._path, offset, length,
                                             self._fdFlags, self._fdMode)
      self._debug('Returning %s' % repr(retval))

      return retval
    except OSError, e:
      self._debug('OSError caught: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def write(self, buf, offset):
    self._debug('opcode: write | path: %s | offset: %d | buf: %s'
                % (self._path, offset, repr(buf)))

    # TODO: Make this write to the cache first, and then update the
    # synclog with the new data region entry on bottom of the synclog
    # queue.

    # TODO: Write to synclog FIRST, then to cache to allow for catching the
    # issue when we crash before we update the synclog.

    # TODO: Append a .N to the conflict.

    # Three cases here:
    #   - The file didn't exist prior to our write.
    #   - The file existed, but was extended.
    #   - The file existed, and an existing block was overwritten.

    bytes_written = 0

    if self._fdFlags & os.O_CREAT:
      self._debug('Adding new file to the synclog...')
      tsumufs.syncLog.addNew('file',
                             filename=self._path,
                             data=buf,
                             start=offset,
                             end=offset+len(buf),
                             length=len(buf))
      self._debug('Done.')
    else:
      # TODO(jtg): make addChange handle sparse inode numbers and update them
      # later.
      nfspath = tsumufs.nfsPathOf(self._path)

      try:
        inode = tsumufs.NameToInodeMap.nameToInode(nfspath)
      except KeyError, e:
        try:
          inode = tsumufs.cacheManager.statFile(self._path).st_ino
        except (IOError, OSError), e:
          inode = -1

      self._debug('Adding change to synclog...')
      tsumufs.syncLog.addChange(self._path,
                                inode,
                                offset,
                                offset+len(buf),
                                buf)
      self._debug('Done.')

    try:
      tsumufs.cacheManager.writeFile(self._path, offset, buf,
                                     self._fdFlags, self._fdMode)
      self._debug('Wrote %d bytes to cache.' % len(buf))
      return len(buf)
    except OSError, e:
      self._debug('OSError caught: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno
    except IOError, e:
      self._debug('IOError caught: %s' % str(e))

      # TODO(jtg): Make this stop the NFS Mount condition on error, rather than
      # raising errno.
      return -e.errno

  def release(self, flags):
    self._debug('opcode: release | flags: %s' % flags)

    # Noop since on NFS close doesn't do much
    return 0

  def fsync(self, isfsyncfile):
    self._debug('opcode: fsync | path: %s | isfsyncfile: %d'
                % (self._path, isfsyncfile))

    self._debug('Returning 0')
    return 0

  def flush(self):
    self._debug('opcode: flush | path: %s' % self._path)

    self._debug('Returning 0')
    return 0

  def fgetattr(self):
    self._debug('opcode: fgetattr')

    try:
      return tsumufs.cacheManager.statFile(self._path)
    except OSError, e:
      self._debug('OSError caught: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def ftruncate(self, size):
    self._debug('opcode: ftruncate | size: %d' % size)

    try:
      return tsumufs.cacheManager.truncateFile(self._path, size)
    except OSError, e:
      self._debug('Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def lock(self, cmd, owner, **kw):
    self._debug('opcode: lock | cmd: %o | owner: %d | kw: %s'
                % (cmd, owner, str(kw)))

    err = -errno.ENOSYS
    self._debug('returning: %d' % err)
    return err
