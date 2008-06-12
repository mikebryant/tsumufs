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

"""TsumuFS, a NFS-based caching filesystem."""

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
  """
  This class represents a file handle for FUSE. With it, we can
  implement stateful file handle management. It also helps to reduce
  some of the complexity that the FuseThread class has obtained.
  """

  _path  = None
  _fdFlags = None
  _fdMode  = None

  def __init__(self, path, flags, mode=None):
    self._path  = path
    self._fdFlags = flags
    self._fdMode  = mode

    self._setName("fusefile <%s>" % self._path)

    try:
      self._debug("opcode: open | flags: %s | mode: %s"
                  % (flags, mode))

      fp = open(tsumufs.nfsMountPoint + self._path, self._flags2mode(flags))
      fp.close()
    except:
      self._debug("*** Unable to open file %s: %s"
                  % (self._path, traceback.format_exc()))

  def _flags2mode(self, flags):
    """
    Borrowed directly from fuse-python's xmp.py script. Credits go to
    Jeff Epler and Csaba Henk.

    This method converts the POSIX standard bitflags for open calls to
    pythonic mode strings.
    """

    md = {os.O_RDONLY: 'r', os.O_WRONLY: 'w', os.O_RDWR: 'w+'}
    m = md[flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)]

    if flags | os.O_APPEND:
      m = m.replace('w', 'a', 1)

    return m

  def read(self, length, offset):
    self._debug("opcode: read | len: %d | offset: %d"
                % (length, offset))

    if tsumufs.nfsAvailable.isSet():
      if tsumufs.cacheManager.shouldCacheFile(self._path):
        tsumufs.cacheManager.cacheFile(self._path)
        filepath = tsumufs.cachePoint + self._path
      else:
        filepath = tsumufs.nfsMountPoint + self._path
    else:
      if tsumufs.cacheManager.isFileCached(self._path):
        filepath = tsumufs.cachePoint + self._path
      else:
        return -errno.ENOENT

    try:
      fp = open(filepath, self._flags2mode(self._fdFlags))
      fp.seek(offset)
      result = fp.read(length)
      fp.close()

      return result
    except OSError, e:
      self._debug("OSError caught: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def write(self, buf, offset):
    self._debug("opcode: write | offset: %d | buf: %s"
                % (offset, repr(buf)))

    try:
      fp = open(tsumufs.nfsMountPoint + self._path,
                self._flags2mode(self._fdFlags))
      fp.seek(offset)
      fp.write(buf)
      fp.close()

      return len(buf)
    except OSError, e:
      self._debug("OSError caught: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def release(self, flags):
    self._debug("opcode: release | flags: %s" % flags)
    # Noop since on NFS close doesn't do much
    return 0

  def fsync(self, isfsyncfile):
    self._debug("opcode: fsync | isfsyncfile: %d" % isfsyncfile)
    return -errno.ENOSYS

  def flush(self):
    self._debug("opcode: flush")
    return -errno.ENOSYS

  def fgetattr(self):
    self._debug("opcode: fgetattr")

    try:
      return tsumufs.cacheManager.statFile(self._path)
    except OSError, e:
      self._debug("OSError caught: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def ftruncate(self, size):
    self._debug("opcode: ftruncate | size: %d" % size)

    try:
      fd = os.open(tsumufs.nfsMountPoint + self._path,
                   self._fdFlags,
                   self._fdMode)
      os.ftruncate(fd, size)
      os.close(fd)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def lock(self, cmd, owner, **kw):
    self._debug("opcode: lock | cmd: %o | owner: %d"
                % (cmd, owner))

    return -errno.ENOSYS
