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
import threading
import cPickle

import logging
logger = logging.getLogger(__name__)

import tsumufs
from extendedattributes import extendedattribute


class PermissionsOverlay(object):
  '''
  Class that provides management for permissions of files in the cache.
  '''

  _lock = None

  overlay = {}     # A hash of inode numbers to FilePermission
                   # objects. This is used to mimic the proper file
                   # permissions on disk while the local filesystem
                   # cannot actually provide these without screwing up
                   # the SyncThread. As a result, we store this to disk
                   # in a serialized format alongside the synclog.

  def __init__(self):
    self._lock = threading.Lock()

    try:
      fp = open(tsumufs.permsPath, 'rb')
      self.overlay = cPickle.load(fp)
      fp.close()
    except IOError, e:
      if e.errno != errno.ENOENT:
        raise

  def __str__(self):
    return '<PermissionsOverlay %s>' % str(self.overlay)

  def _checkpoint(self):
    '''
    Checkpoint the permissions overlay to disk.
    '''

    fp = open(tsumufs.permsPath, 'wb')
    cPickle.dump(self.overlay, fp)
    fp.close()

  def _getFileInum(self, fusepath):
    '''
    Return the inode number of the file specified in the cache.

    Returns:
      The inode number.

    Raises:
      OSError
    '''

    cachepath = tsumufs.cachePathOf(fusepath)
    inum = os.lstat(cachepath).st_ino

    return inum

  def getPerms(self, fusepath):
    '''
    Return a FilePermission object that contains the uid, gid, and mode of the
    file in the cache. Expects a fusepath and converts that to a cachepath
    directly by itself.

    Returns:
      A FilePermission instance.

    Raises:
      KeyError, OSError
    '''

    try:
      self._lock.acquire()

      inum = self._getFileInum(fusepath)
      return self.overlay[inum]

    finally:
      self._lock.release()

  def setPerms(self, fusepath, uid, gid, mode):
    '''
    Store a new FilePermission object, indexed by it's inode number.

    Returns:
      Nothing

    Raises:
      Nothing
    '''

    try:
      self._lock.acquire()

      inum = self._getFileInum(fusepath)

      perms = tsumufs.FilePermission()
      perms.uid = uid
      perms.gid = gid
      perms.mode = mode

      self.overlay[inum] = perms
      self._checkpoint()

    finally:
      self._lock.release()

  def removePerms(self, inum):
    '''
    Remove a FilePermission object from the overlay, based upon it's inode
    number.

    Returns:
      Nothing

    Raises:
      KeyError
    '''

    try:
      self._lock.acquire()

      del self.overlay[inum]
      self._checkpoint()

    finally:
      self._lock.release()


@extendedattribute('root', 'tsumufs.perms-overlay')
def xattr_permsOverlay(type_, path, value=None):
  if not value:
    return repr(PermissionsOverlay.overlay)

  return -errno.EOPNOTSUPP
