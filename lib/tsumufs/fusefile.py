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


class FuseFile(object):
  """
  This class represents a file handle for FUSE. With it, we can
  implement stateful file handle management. It also helps to reduce
  some of the complexity that the FuseThread class has obtained.
  """

  _path  = None
  _flags = None

  def __init__(self, path, flags, *mode):
    try:
      self._debug("opcode: open | path: %s | flags: %o"
                  % (self._path, flags))

      self._path = path
      self._flags = flags

      fp = open(tsumufs.nfsMountPoint + path, self._flag2mode(flags))
      fp.close()
    except:
      self._debug("*** Unable to open file %s: %s"
                  % (self._path, traceback.format_exc()))

  def _flag2mode(self, flags):
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

  def _debug(self, args):
    if tsumufs.debugMode:
      syslog.syslog("fusefile: " + args)

  def read(self, length, offset):
    self._debug("opcode: read | path: %s | len: %d | offset: %d"
                % (self._path, length, offset))
    
    fp = open(tsumufs.nfsMountPoint + self._path, "r")
    fp.seek(offset)
    result = fp.read(length)
    fp.close()

    return result

  def write(self, buf, offset):
    self._debug("opcode: write | path: %s | buf: '%s' | offset: %d"
                % (self._path, buf, offset))

    fp = open(tsumufs.nfsMountPoint + self._path, "w+", 8192)
    fp.seek(offset)
    result = fp.write(buf)
    fp.close()

    return len(buf)

  def release(self, flags):
    self._debug("opcode: release | path: %s | flags: %s" % (self._path, flags))
    # Noop since on NFS close doesn't do much
    return 0

  def fsync(self, isfsyncfile):
    self._debug("opcode: fsync | path: %s | isfsyncfile: %d"
                % (self._path, isfsyncfile))
    return -errno.ENOSYS

  def flush(self):
    self._debug("opcode: flush")
    return -errno.ENOSYS

  def fgetattr(self):
    self._debug("opcode: fgetattr | path: %s" % self._path)
    return os.lstat(tsumufs.nfsMountPoint + self._path)

  def ftruncate(self):
    self._debug("opcode: ftruncate | path: %s | size: %d"
                % (self._path, size))
    fp = os.open(tsumufs.nfsMountPoint + self._path, "r+")
    fd = os.fdopen(fp)
    result = os.ftruncate(fd, size)

#   def lock(self, cmd, owner, **kw):
#     self._debug("opcode: lock | cmd: %o | owner: %d"
#                 % (cmd, owner))
#     return -ENOSYS
