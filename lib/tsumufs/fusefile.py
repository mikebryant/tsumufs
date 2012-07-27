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
import logging
logger = logging.getLogger(__name__)

import fuse
from fuse import Fuse

import tsumufs
from metrics import benchmark


class FuseFile(object):
  '''
  This class represents a file handle for FUSE. With it, we can
  implement stateful file handle management. It also helps to reduce
  some of the complexity that the FuseThread class has obtained.
  '''

  _path      = None
  _fdFlags   = None
  _fdMode    = None
  _uid       = None
  _gid       = None
  _pid       = None
  _isNewFile = None

  @benchmark
  def __init__(self, path, flags, mode=None, uid=None, gid=None, pid=None):
    self._path  = path
    self._fdFlags = flags
    self._fdMode  = mode
    self._uid = uid
    self._gid = gid
    self._pid = pid

    self._setName('FuseFile <%s> ' % self._path)

    # NOTE: If mode == None, then we were called as a creat(2) system call,
    # otherwise we were called as an open(2) system call.

    # Install our custom exception handler so that any exceptions are
    # output to the syslog rather than to /dev/null.
    sys.excepthook = tsumufs.syslogExceptHook

    if mode == None:
      logging.debug(('opcode: open | flags: %s | mode: %o | '
                   'uid: %d | gid: %d | pid: %d')
                  % (self._flagsToString(), mode or 0,
                     self._uid, self._gid, self._pid))
    else:
      logging.debug(('opcode: creat | flags: %s | mode: %o | '
                   'uid: %d | gid: %d | pid: %d')
                  % (self._flagsToString(), mode or 0,
                     self._uid, self._gid, self._pid))

    access_mode = 0

    if self._fdFlags & (os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_APPEND):
      access_mode |= os.W_OK

    if self._fdFlags & os.O_RDONLY:
      access_mode |= os.R_OK

    # Verify access to the directory
    logging.debug('Verifying access to directory %s' % os.path.dirname(path))
    tsumufs.cacheManager.access(self._uid,
                                os.path.dirname(path),
                                access_mode | os.X_OK)

    if not self._fdFlags & os.O_CREAT:
      logging.debug('Checking access on file since we didn\'t create it.')
      tsumufs.cacheManager.access(self._uid, path, access_mode)

    logging.debug('Calling fakeopen')
    tsumufs.cacheManager.fakeOpen(path, self._fdFlags, self._fdMode,
                                  self._uid, self._gid)

    if self._fdFlags & os.O_TRUNC:
      self.ftruncate(0)

    # If we were a new file, create a new change in the synclog for the new file
    # entry.
    if self._fdFlags & os.O_CREAT:
      logging.debug('Adding permissions to the PermissionsOverlay.')
      tsumufs.permsOverlay.setPerms(self._path, self._uid, self._gid,
                                    self._fdMode)

      logging.debug('Adding a new change to the log as user wanted O_CREAT')
      tsumufs.syncLog.addNew('file', filename=self._path)

      self._isNewFile = True

    # Rip out any O_TRUNC options after we do the initial open -- O_TRUNC is
    # dangerous to do in this case, because if we get multiple write calls, we
    # just pass in the _fdMode raw, which causes multiple O_TRUNC calls to the
    # underlying file, resulting in data loss. We do the same for O_CREAT, as it
    # can also cause problems later on.

    self._fdFlags = self._fdFlags & (~os.O_TRUNC)
    self._fdFlags = self._fdFlags & (~os.O_CREAT)

  def _flagsToString(self):
    string = ''

    for flag in dir(os):
      if flag.startswith('O_'):
        flag_value = eval('os.%s' % flag)

        if self._fdFlags & flag_value:
          string += '|%s' % flag

    return string[1:]

  @benchmark
  def read(self, length, offset):
    logging.debug('opcode: read | path: %s | len: %d | offset: %d'
                % (self._path, length, offset))

    try:
      retval = tsumufs.cacheManager.readFile(self._path, offset, length,
                                             self._fdFlags, self._fdMode)
      logging.debug('Returning %s' % repr(retval))

      return retval
    except OSError, e:
      logging.debug('OSError caught: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def write(self, new_data, offset):
    logging.debug('opcode: write | path: %s | offset: %d | buf: %s'
                % (self._path, offset, repr(new_data)))

    # Three cases here:
    #   - The file didn't exist prior to our write.
    #   - The file existed, but was extended.
    #   - The file existed, and an existing block was overwritten.

    nfspath = tsumufs.nfsPathOf(self._path)
    statgoo = tsumufs.cacheManager.statFile(self._path)

    try:
      inode = tsumufs.NameToInodeMap.nameToInode(nfspath)
    except KeyError, e:
      try:
        inode = statgoo.st_ino
      except (IOError, OSError), e:
        inode = -1

    if not tsumufs.syncLog.isNewFile(self._path):
      logging.debug('Reading offset %d, length %d from %s.'
                  % (offset, len(new_data), self._path))
      old_data = tsumufs.cacheManager.readFile(self._path,
                                               offset,
                                               len(new_data),
                                               os.O_RDONLY)
      logging.debug('From cacheManager.readFile got %s' % repr(old_data))

      # Pad missing chunks on the old_data stream with NULLs, as NFS
      # would. Unfortunately during resyncing, we'll have to consider regions
      # past the end of a file to be NULLs as well. This allows us to merge data
      # regions cleanly without rehacking the model.

      if len(old_data) < len(new_data):
        logging.debug(('New data is past end of file by %d bytes. '
                     'Padding with nulls.')
                    % (len(new_data) - len(old_data)))
        old_data += '\x00' * (len(new_data) - len(old_data))

      logging.debug('Adding change to synclog [ %s | %d | %d | %d | %s ]'
                  % (self._path, inode, offset, offset+len(new_data),
                     repr(old_data)))

      tsumufs.syncLog.addChange(self._path,
                                inode,
                                offset,
                                offset+len(new_data),
                                old_data)
    else:
      logging.debug('We\'re a new file -- not adding a change record to log.')

    try:
      tsumufs.cacheManager.writeFile(self._path, offset, new_data,
                                     self._fdFlags, self._fdMode)
      logging.debug('Wrote %d bytes to cache.' % len(new_data))

      return len(new_data)
    except OSError, e:
      logging.debug('OSError caught: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno
    except IOError, e:
      logging.debug('IOError caught: %s' % str(e))

      # TODO(jtg): Make this stop the NFS Mount condition on error, rather than
      # raising errno.
      return -e.errno

  @benchmark
  def release(self, flags):
    logging.debug('opcode: release | flags: %s' % flags)

    # Noop since on NFS close doesn't do much
    return 0

  @benchmark
  def fsync(self, isfsyncfile):
    logging.debug('opcode: fsync | path: %s | isfsyncfile: %d'
                % (self._path, isfsyncfile))

    logging.debug('Returning 0')
    return 0

  @benchmark
  def flush(self):
    logging.debug('opcode: flush | path: %s' % self._path)

    logging.debug('Returning 0')
    return 0

  @benchmark
  def fgetattr(self):
    logging.debug('opcode: fgetattr')

    try:
      return tsumufs.cacheManager.statFile(self._path)
    except OSError, e:
      logging.debug('OSError caught: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def ftruncate(self, size):
    logging.debug('opcode: ftruncate | size: %d' % size)

    try:
      statgoo = tsumufs.cacheManager.statFile(self._path)

      # Get inode number
      try:
        inum = tsumufs.NameToInodeMap.nameToInode(tsumufs.nfsPathOf(self._path))
      except KeyError, e:
        try:
          inum = statgoo.st_ino
        except (IOError, OSError), e:
          inum = -1

      except Exception, e:
        exc_info = sys.exc_info()

        logging.debug('*** Unhandled exception occurred')
        logging.debug('***     Type: %s' % str(exc_info[0]))
        logging.debug('***    Value: %s' % str(exc_info[1]))
        logging.debug('*** Traceback:')

        for line in traceback.extract_tb(exc_info[2]):
          logging.debug('***    %s(%d) in %s: %s' % line)

      # Add the truncated data to the synclog if this is an old file...
      if not tsumufs.syncLog.isNewFile(self._path):
        if size < statgoo.st_size:
          data = tsumufs.cacheManager.readFile(self._path, size,
                                               (statgoo.st_size - size),
                                               os.O_RDONLY)
          tsumufs.syncLog.addChange(self._path, inum, size, statgoo.st_size, data)
        elif size > statgoo.st_size:
          tsumufs.syncLog.addChange(self._path, inum, statgoo.st_size, size,
                                    '\x00' * (size - statgoo.st_size))
        else:
          return 0

      # ...and truncate the file
      tsumufs.cacheManager.truncateFile(self._path, size)
      return 0

    except OSError, e:
      logging.debug('truncate: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

    except Exception, e:
      exc_info = sys.exc_info()

      logging.debug('*** Unhandled exception occurred')
      logging.debug('***     Type: %s' % str(exc_info[0]))
      logging.debug('***    Value: %s' % str(exc_info[1]))
      logging.debug('*** Traceback:')

      for line in traceback.extract_tb(exc_info[2]):
        logging.debug('***    %s(%d) in %s: %s' % line)

    return 0

  @benchmark
  def lock(self, cmd, owner, **kw):
    logging.debug('opcode: lock | cmd: %o | owner: %d | kw: %s'
                % (cmd, owner, str(kw)))

    # TODO(jtg): Implement this.
    logging.debug('Returning -ENOSYS')
    return -errno.ENOSYS
