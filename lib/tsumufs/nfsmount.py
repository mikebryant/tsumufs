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
import errno
import sys
import stat
import syslog
import thread
import threading
import dataregion

import tsumufs


class NFSMountError(Exception):
  pass


class NFSMount(tsumufs.Debuggable):
  '''
  Represents the NFS mount iself.

  This object is responsible for accessing files and data in the NFS
  mount. It is also responsible for setting the connectedEvent to
  False in case of an NFS access error.
  '''

  _fileLocks = {}
  _lockLock  = threading.RLock()

  def __init__(self):
    pass

  def lockFile(self, filename):
    '''
    Method to lock a file. Blocks if the file is already locked.

    Args:
      filename: The complete pathname to the file to lock.

    Returns:
      A boolean value.
    '''

    # Force the interpreter to do the following atomically
    old_interval = sys.getcheckinterval()
    sys.setcheckinterval(1000)

    try:
#       tb = self._getCaller()
#       self._debug('Locking file %s (from: %s(%d): in %s <%d>).'
#                   % (filename, tb[0], tb[1], tb[2], thread.get_ident()))

      try:
        self._fileLocks[filename].acquire()
      except KeyError:
        self._fileLocks[filename] = threading.RLock()
        self._fileLocks[filename].acquire()

    finally:
      sys.setcheckinterval(old_interval)

  def unlockFile(self, filename):
    '''
    Method to unlock a file.

    Args:
      filename: The complete pathname to the file to unlock.

    Returns:
      A boolean value.
    '''

    # Force the interpreter to do the following atomically
    old_interval = sys.getcheckinterval()
    sys.setcheckinterval(1000)

    try:
#       tb = self._getCaller()
#       self._debug('Unlocking file %s (from: %s(%d): in %s <%d>).'
#                   % (filename, tb[0], tb[1], tb[2], thread.get_ident()))

      self._fileLocks[filename].release()

    finally:
      sys.setcheckinterval(old_interval)

  def pingServerOK(self):
    '''
    Method to verify that the NFS server is available.
    '''
    return True

  def nfsCheckOK(self):
    '''
    Method to verify that the NFS server is available and returning
    valid responses.
    '''
    return True

  def readFileRegion(self, filename, start, end):
    '''
    Method to read a region of a file from the NFS mount. Additionally
    adds the inode to filename mapping to the InodeMap singleton.

    Args:
      filename: the complete pathname to the file to read from.
      start: the beginning offset to read from.
      end: the ending offset to read from.

    Returns:
      A string containing the data read.

    Raises:
      NFSMountError: An error occurred during an NFS call which is
        unrecoverable.
      RangeError: The start and end provided are invalid.
      IOError: Usually relating to permissions issues on the file.
    '''

    try:
      self.lockFile(filename)

      try:
        nfspath = tsumufs.nfsPathOf(filename)

        fp = open(nfspath, 'r')
        fp.seek(start)
        result = fp.read(end - start)
        fp.close()

        return result

      except OSError, e:
        if e.errno in (errno.EIO, errno.ESTALE):
          self._debug('Got %s while reading a region from %s.' %
                      (str(e), filename))
          self._debug('Triggering a disconnect.')

          tsumufs.nfsAvailable.clear()
          tsumufs.nfsAvailable.notifyAll()
          raise tsumufs.NFSMountError()
        else:
          raise

    finally:
      self.unlockFile(filename)

  def writeFileRegion(self, filename, start, end, data):
    '''
    Method to write a region to a file on the NFS mount. Additionally
    adds the resulting inode to filename mapping to the InodeMap
    singleton.

    Args:
      filename: the complete pathname to the file to write to.
      start: the beginning offset to write to.
      end: the ending offset to write to.
      data: the data to write.

    Raises:
      NFSMountError: An error occurred during an NFS call.
      RangeError: The start and end provided are invalid.
      OSError: Usually relating to permissions on the file.
    '''

    if end - start > len(data):
      raise dataregion.RangeError('The length of data specified in start and '
                                  'end does not match the data length.')

    try:
      self.lockFile(filename)

      try:
        nfspath = tsumufs.nfsPathOf(filename)

        fp = open(nfspath, 'r+')
        fp.seek(start)
        fp.write(data)
        fp.close()

      except OSError, e:
        if e.errno in (errno.EIO, errno.ESTALE):
          self._debug('Got %s while writing a region to %s.' %
                      (str(e), filename))
          self._debug('Triggering a disconnect.')

          tsumufs.nfsAvailable.clear()
          tsumufs.nfsAvailable.notifyAll()

          raise tsumufs.NFSMountError()
        else:
          raise

    finally:
      self.unlockFile(filename)

  def truncateFile(self, fusepath, newsize):
    '''
    Truncate a file to newsize.
    '''

    try:
      self.lockFile(fusepath)

      try:
        nfspath = tsumufs.nfsPathOf(fusepath)

        fp = open(nfspath, 'r+')
        fp.truncate(newsize)
        fp.close()

      except OSError, e:
        if e.errno in (errno.EIO, errno.ESTALE):
          self._debug('Got %s while writing a region to %s.' %
                      (str(e), nfspath))
          self._debug('Triggering a disconnect.')

          tsumufs.nfsAvailable.clear()
          tsumufs.nfsAvailable.notifyAll()

          raise tsumufs.NFSMountError()
        else:
          raise

    finally:
      self.unlockFile(fusepath)

  def mount(self):
    '''
    Quick and dirty method to actually mount the real NFS connection
    somewhere else on the filesystem. For now, this just shells out to
    the mount(8) command to do its dirty work.
    '''

    try:
      os.stat(tsumufs.nfsMountPoint)
    except OSError, e:
      if e.errno == errno.ENOENT:
        self._debug('Mount point %s was not found -- creating'
                   % tsumufs.nfsMountPoint)
        try:
          os.mkdir(tsumufs.nfsMountPoint)
        except OSError, e:
          self._debug('Unable to create mount point: %s'
                     % os.strerror(e.errno))
          return False
      elif e.errno == errno.EACCES:
        self._debug('Mount point %s unavailable: %s'
                   % (tsumufs.nfsMountPoint,
                      os.strerror(e.errno)))
        return False

    try:
      # TODO(ajs): for leopard, cmd = '/sbin/mount -t nfs'
      cmd = '/usr/bin/sudo -u root /bin/mount -t nfs'
      if tsumufs.mountOptions != None:
        cmd += ' -o ' + tsumufs.mountOptions
      cmd += ' ' + tsumufs.mountSource + ' ' + tsumufs.nfsMountPoint

      self._debug(cmd)
      rc = os.system(cmd) >> 8
    except OSError, e:
      self._debug('Mount of NFS failed: %s.' % os.strerror(e.errno))
      return False
    else:
      if rc != 0:
        self._debug('Mount of NFS failed -- mount returned nonzero: %s' % rc)
        return False
      else:
        self._debug('Mount of NFS succeeded.')
        return True

  def unmount(self):
    '''
    Quick and dirty method to actually UNmount the real NFS connection
    somewhere else on the filesystem.
    '''

    self._debug('Unmounting NFS mount from %s' %
               tsumufs.nfsMountPoint)
    rc = os.system('/usr/bin/sudo /bin/umount %s' % tsumufs.nfsMountPoint)

    if rc != 0:
      self._debug('Unmount of NFS failed.')
      return False
    else:
      self._debug('Unmount of NFS succeeded.')
      return True

    self._debug('Invalidating name to inode map')
    tsumufs.NameToInodeMap.invalidate()
