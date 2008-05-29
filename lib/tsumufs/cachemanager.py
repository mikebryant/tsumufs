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
import os.path
import shutil
import errno
import stat
import syslog
import threading

import tsumufs


class CacheManager(tsumufs.Debuggable):
  """
  Class designed to handle management of the cache. All caching
  operations (and decaching operations) are performed here.
  """

  _statTimeout = 60        # The number of seconds we use the cached
                           # copy's stat information for before we
                           # attempt to update it from the nfs mount.

  _cachedFiles = {}        # A hash of paths to unix timestamps of
                           # when we last cached the file.

  _fileLocks = {}          # A hash of paths to locks to serialize
                           # access to files in the cache.

  def __init__(self):
    pass

  def isFileCached(self, path):
    """
    Check to see if the file referenced by path is actually cached.

    Path is expected to be an absolute path into the filesystem from
    the view seen from FUSE. Ie: all "absolute paths" are actually
    relative to the tsumufs mountpoint root.

    Returns:
      Boolean. True if the file is cached. False otherwise.

    Raises:
      OSError if there was an issue statting the file in question.
    """

    # Lock the file for access
    self.lockFile(path)

    if self._cachedFiles.has_key(path):
      self.unlockFile(path)
      return True
    else:
      try:
        os.lstat("%s/%s" % (tsumufs.cacheBaseDir, path))
      except OSError, e:
        if e.errno == errno.ENOENT:
          if self._cachedFiles.has_key(path):
            del self._cachedFiles[path]

          self.unlockFile(path)
          return False
        else:
          self._debug("Caught OSError: errno %d: %s"
                      % (e.errno, e.strerror))
          
      else:
        self.unlockFile(path)
        raise

      self._cachedFiles[path] = True
      self.unlockFile(path)
      return True

  def cacheFile(self, path):
    """
    Cache the file referenced by path.

    This method locks the file for reading, determines what type it
    is, and attempts to cache it. Note that if there was an issue
    reading from the NFSMount, this method will mark the NFS mount as
    being unavailble.

    Note: The touch cache isn't implemented here at the moment. As a
    result, the entire cache is considered permacache for now.

    Note: NFS error checking and disable are not handled here for the
    moment. Any errors that would ordinarily shut down the NFS mount
    are just reported as normal OSErrors, aside from ENOENT.

    Returns:
      None

    Raises:
      OSError if there was an issue attempting to copy the file
      across to cache.
    """

    nfsfilename   = "%s/%s" % (tsumufs.nfsMountPoint, path)
    cachefilename = "%s/%s" % (tsumufs.cacheBaseDir, path)

    if not self.shouldCacheFile(path):
      return False

    try:
      try:
        self.lockFile(path)

        if os.path.isfile(nfsfilename) or os.path.islink(nfsfilename):
          shutil.copy2(nfsfilename, cachefilename)
          shutil.copystat(nfsfilename, cachefilename)

          stat = os.lstat(nfsfilename)
          os.chown(cachefilename, stat.uid)
          os.chgrp(cachefilename, stat.gid)
        
        elif os.path.isdir(nfsfilename):
          os.mkdir(cachefilename)
          shutil.copystat(nfsfilename, cachefilename)

          stat = os.lstat(nfsfilename)
          os.chown(cachefilename, stat.uid)
          os.chgrp(cachefilename, stat.gid)

        self._cachedFiles[path] = True
      except OSError, e:
        self._debug("Caught OSError: errno %d: %s"
                    % (e.errno, e.strerror))
    finally:
      self.unlockFile(path)
      
  def removeCachedFile(self, path):
    """
    Remove the cached file referenced by path from the cache.

    This method locks the file, determines what type it is, and
    attempts to decache it.

    Note: The touch cache isn't implemented here at the moment. As a
    result, the entire cache is considered permacache for now.

    Returns:
      None

    Raises:
      OSError if there was an issue attempting to remove the file
      from cache.
    """

    self.lockFile(path)
    cachefilename = "%s/%s" % (tsumufs.cacheBaseDir, path)

    try:
      try:
        if os.path.isfile(cachefilename) or os.path.islink(cachefilename):
          os.unlink(cachefilename)
        elif os.path.isdir(cachefilename):
          # Recursively descend into the path, removing all of the files
          # and dirs from the cache as well as this one.

          pass

        del self._cachedFiles[path]

      except OSError, e:
        self._debug("Caught OSError: errno %d: %s"
                    % (e.errno, e.strerror))
        
        if e.errno == errno.ENOENT:
          del self._cachedFiles[path]
        else:
          raise

    finally:
      self.unlockFile(path)

  def shouldCacheFile(self, path):
    """
    Method to determine if a file referenced by path should be
    cached.

    Note: Currently this method only returns True, and none of the
    cachespec information is actually processed or used.

    Returns:
      Boolean. True if the file should be cached.

    Raises:
      None
    """

    self.lockFile(self, path)

    if self._cachedFiles.has_key(path):
      self.unlockFile(self, path)
      return False
    else:
      self.unlockFile(self, path)
      return True

  def lockFile(self, path):
    """
    Lock the file for access exclusively.

    This prevents multiple FUSE threads from clobbering
    one-another. Note that this method blocks until a
    previously-locked file is unlocked.

    Returns:
      None

    Raises:
      None
    """

    try:
      self._fileLocks[path].acquire()
    except KeyError:
      self._fileLocks[path] = threading.Lock()
      self._fileLocks[path].acquire()

  def unlockFile(self, path):
    """
    Unlock the file for access.

    The inverse of lockFile. Releases a lock if one had been
    previously acquired.

    Returns:
      None

    Raises:
      None
    """

    self._fileLocks[path].release()
