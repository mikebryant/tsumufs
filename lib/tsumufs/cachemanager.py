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
import os.path
import shutil
import errno
import stat
import syslog
import threading
import time

import tsumufs


class CacheManager(tsumufs.Debuggable):
  '''
  Class designed to handle management of the cache. All caching
  operations (and decaching operations) are performed here.
  '''

  _statTimeout = 60        # The number of seconds we use the cached
                           # copy's stat information for before we
                           # attempt to update it from the nfs mount.

  _cachedDirents = {}      # A hash of paths to unix timestamps of
                           # when we last cached the file.

  _fileLocks = {}          # A hash of paths to locks to serialize
                           # access to files in the cache.

  def __init__(self):
    try:
      os.stat(tsumufs.cachePoint)
    except OSError, e:
      if e.errno == errno.ENOENT:
        self._debug('Cache point %s was not found -- creating'
                    % tsumufs.cachePoint)

        try:
          os.mkdir(tsumufs.cachePoint)
        except OSError, e:
          self._debug('Unable to create cache point: %s (exiting)'
                      % os.strerror(e.errno))
          raise e

      elif e.errno == errno.EACCES:
        self._debug('Cache point %s is unavailable: %s (exiting)'
                    % (tsumufs.cachePoint,
                       os.strerror(e.errno)))
        raise e

  def statFile(self, fusepath):
    '''
    Cache the stat referenced by fusepath.

    This method locks the file for reading, returns the stat result
    (as returned by lstat()), enters the stat entry into the cache,
    and unlocks the file.
    '''

    # TODO: Make this update the inode -> file mappings.

    self._lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath, for_stat=True)
      self._validateCache(fusepath, opcodes)
      realpath = self._generatePath(fusepath, opcodes)

      self._debug('Statting %s' % realpath)
      return os.lstat(realpath)
    finally:
      self._unlockFile(fusepath)

  def getDirents(self, fusepath):
    '''
    Return the dirents from a directory's contents if cached.
    '''

    self._lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)
      self._validateCache(fusepath, opcodes)
      realpath = self._generatePath(fusepath, opcodes)

      if 'use-nfs' in opcodes:
        self._debug('use-nfs, so reading from %s' % realpath)
        return os.listdir(realpath)
      elif 'use-cache' in opcodes:
        self._debug('use-cache, so reading from memcache at key %s' % fusepath)

        if self._cachedDirents.has_key(fusepath):
          return self._cachedDirents[fusepath]

    finally:
      self._unlockFile(fusepath)

  def readFile(self, fusepath, offset, length, mode):
    '''
    Read a chunk of data from the file referred to by path.

    This method acts very much like the typical idiom:

      fp = open(file, mode)
      fp.seek(offset)
      result = fp.read(length)
      return result

    Except it works in respect to the cache and the NFS mount. If the
    file is available from NFS and should be cached to disk, it will
    be cached and then read from there.

    Otherwise, NFS reads are done directly.

    Returns:
      The data requested.

    Raises:
      OSError on error reading the data.
    '''

    self._lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)
      self._validateCache(fusepath, opcodes)
      realpath = self._generatePath(fusepath, opcodes)

      self._debug('Reading file contents from %s' % realpath)

      fp = open(realpath, mode)
      fp.seek(offset)
      result = fp.read(length)
      fp.close()

      return result
    finally:
      self._unlockFile(fusepath)

  def _cacheDir(self, fusepath):
    '''
    Cache the directory referenced by path.

    If the directory should not be cached to disk (as specified in the
    cachespec) then only the contents of the directory hash table will
    be stored in the _cachedFiles hash.

    Returns:
      None

    Raises:
      OSError - when an error operating on the filesystem occurs.
    '''

    self._lockFile(fusepath)

    try:
      nfspath   = self._nfsPathOf(fusepath)
      cachepath = self._cachePathOf(fusepath)
      stat      = os.lstat(nfspath)

      self._debug('nfspath = %s' % nfspath)
      self._debug('cachepath = %s' % cachepath)

      if fusepath == '/':
        self._debug('Asking to cache root -- skipping the cache to '
                    'disk operation, but caching data in memory.')
      else:
        os.mkdir(cachepath)
        shutil.copystat(nfspath, cachepath)
        os.chown(cachepath, stat.st_uid, stat.st_gid)

      self._debug('Caching directory %s to disk.' % fusepath)
      self._cachedDirents[fusepath] = os.listdir(nfspath)

    finally:
      self._unlockFile(fusepath)

  def _cacheFile(self, fusepath):
    '''
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
      Nothing.

    Raises:
      OSError if there was an issue attempting to copy the file
      across to cache.
    '''

    self._lockFile(fusepath)

    try:
      self._debug('Caching file %s to disk.' % fusepath)

      curstat = os.lstat(self._nfsPathOf(fusepath))

      if (stat.S_ISREG(curstat.st_mode) or
          stat.S_ISLNK(curstat.st_mode)):
        shutil.copy2(self._nfsPathOf(fusepath), self._cachePathOf(fusepath))
        shutil.copystat(self._nfsPathOf(fusepath), self._cachePathOf(fusepath))
        os.chown(self._cachePathOf(fusepath), curstat.st_uid, curstat.st_gid)
      elif stat.S_ISDIR(curstat.st_mode):
        # Caching a directory to disk -- call cacheDir instead.
        self._debug('Request to cache a directory -- calilng _cacheDir')
        self._cacheDir(fusepath)

    finally:
      self._unlockFile(fusepath)

  def _removeCachedFile(self, fusepath):
    '''
    Remove the cached file referenced by fusepath from the cache.

    This method locks the file, determines what type it is, and
    attempts to decache it.

    Note: The touch cache isn't implemented here at the moment. As a
    result, the entire cache is considered permacache for now.

    Returns:
      None

    Raises:
      OSError if there was an issue attempting to remove the file
      from cache.
    '''

    self._lockFile(fusepath)

    try:
      cachefilename = self._cachePathOf(fusepath)

      if os.path.isfile(cachefilename) or os.path.islink(cachefilename):
        os.unlink(cachefilename)
      elif os.path.isdir(cachefilename):
        # TODO: Recursively descend into the path, removing all of the files and
        # dirs from the cache as well as this one.
        pass

    finally:
      self._unlockFile(fusepath)

  def _shouldCacheFile(self, fusepath):
    '''
    Method to determine if a file referenced by fusepath should be
    cached, as aoccording to the cachespec file.

    Note: Currently this method only returns True, and none of the
    cachespec information is actually processed or used.

    Returns:
      Boolean. True if the file should be cached.

    Raises:
      None
    '''

    # TODO: Check against the cachespec!
    return True

  def _validateCache(self, fusepath, opcodes=None):
    if opcodes == None:
      opcodes = self._genCacheOpcodes(fusepath)

    self._debug('Opcodes are: %s' % opcodes)

    for opcode in opcodes:
      if opcode == 'remove-cache':
        self._debug('Removing cached file %s' % fusepath)
        self._removeCachedFile(fusepath)
      if opcode == 'cache-file':
        self._debug('Caching file %s' % fusepath)
        self._cacheFile(fusepath)
      if opcode == 'merge-conflict':
        # TODO: handle a merge-conflict?
        self._debug('Merge/conflict on %s' % fusepath)

  def _generatePath(self, fusepath, opcodes=None):
    if opcodes == None:
      opcodes = self._genCacheOpcodes(fusepath)

    self._debug('Opcodes are: %s' % opcodes)

    for opcode in opcodes:
      if opcode == 'enoent':
        self._debug('ENOENT on %s' % fusepath)
        raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))
      if opcode == 'use-nfs':
        self._debug('Returning nfs path for %s' % fusepath)
        return self._nfsPathOf(fusepath)
      if opcode == 'use-cache':
        self._debug('Returning cache path for %s' % fusepath)
        return self._cachePathOf(fusepath)

  def _genCacheOpcodes(self, fusepath, for_stat=False):
    '''
    Method encapsulating cache operations and determination of whether
    or not to use a cached copy, an nfs copy, update the cache, or
    raise an enoent.

    The string opcodes are as follows:
      enoent         - caller should raise an OSError with ENOENT as the
                       error code.
      use-nfs        - caller should use the nfs filename for file
                       operations.
      use-cache      - caller should use the cache filename for file
                       operations.
      cache-file     - caller should cache the nfs file to disk and
                       overwrite the local copy unconditionally.
      remove-cache   - caller should remove the cached copy
                       unconditionally.
      merge-conflict - undefined at the moment?

    Returns:
      A tuple containing strings.

    Raises:
      Nothing
    '''

    # if not cachedFile and not nfsAvailable raise -ENOENT
    if not self._isCachedToDisk(fusepath) and not tsumufs.nfsAvailable.isSet():
      self._debug('File not cached, no nfs -- enoent')
      return ['enoent']

    # if not cachedFile and not shouldCache
    if not self._isCachedToDisk(fusepath) and not self._shouldCacheFile(fusepath):
      if tsumufs.nfsAvailable.isSet():
        self._debug('File not cached, should not cache -- use nfs.')
        return ['use-nfs']

    # if not cachedFile and     shouldCache
    if not self._isCachedToDisk(fusepath) and self._shouldCacheFile(fusepath):
      if tsumufs.nfsAvailable.isSet():
        if for_stat == True:
          self._debug('Returning use-nfs, as this is for stat.')
          return ['use-nfs']

        self._debug(('File not cached, should cache, nfs avail '
                     '-- cache file, use cache.'))
        return ['cache-file', 'use-cache']
      else:
        self._debug('File not cached, should cache, no nfs -- enoent')
        return ['enoent']

    # if     cachedFile and not shouldCache
    if self._isCachedToDisk(fusepath) and not self._shouldCacheFile(fusepath):
      if tsumufs.nfsAvailable.isSet():
        self._debug(('File cached, should not cache, nfs avail '
                     '-- remove cache, use nfs'))
        return ['remove-cache', 'use-nfs']
      else:
        self._debug(('File cached, should not cache, no nfs '
                     '-- remove cache, enoent'))
        return ['remove-cache', 'enoent']

    # if     cachedFile and     shouldCache
    if self._isCachedToDisk(fusepath) and self._shouldCacheFile(fusepath):
      if tsumufs.nfsAvailable.isSet():
        if self._dataChanged(fusepath):
          # TODO: Make this really check for dirtiness of the file
          if False: # tsumufs.syncQueue.cachedFileDirty(fusepath):
            self._debug('Merge conflict detected.')
            return ['merge-conflict']
          else:
            if for_stat == True:
              self._debug('Returning use-nfs, as this is for stat.')
              return ['use-nfs']

            self._debug(('Cached, should cache, nfs avail, nfs changed, '
                         'cache clean -- recache, use cache'))
            return ['cache-file', 'use-cache']

    self._debug('Using cache by default, as no other cases matched.')
    return ['use-cache']

  def _dataChanged(self, fusepath):
    self._lockFile(fusepath)

    try:
      cachestat = os.lstat(self._cachePathOf(fusepath))
      nfsstat   = os.lstat(self._nfsPathOf(fusepath))

      if ((cachestat.st_blocks != nfsstat.st_blocks) or
          (cachestat.st_mtime != nfsstat.st_mtime) or
          (cachestat.st_size != nfsstat.st_size) or
          (cachestat.st_ino != nfsstat.st_ino)):
        return True
      else:
        return False
    finally:
      self._unlockFile(fusepath)

  def _nfsPathOf(self, fusepath):
    '''
    Quick one-off method to help with translating FUSE-side pathnames
    to VFS pathnames.

    Returns:
      A string containing the absolute path to the file on the NFS
      mount.

    Raises:
      Nothing
    '''

    # Catch the case that the fusepath is absolute (which it should be)
    if fusepath[0] == '/':
      rhs = fusepath[1:]
    else:
      rhs = fusepath

    transpath = os.path.join(tsumufs.nfsMountPoint, rhs)
    return transpath

  def _cachePathOf(self, fusepath):
    '''
    Quick one-off method to help with translating FUSE-side pathnames
    to VFS pathnames.

    This method returns the cache-side VFS pathname for the given
    fusepath.

    Returns:
      A string containing the absolute path to the file on the cache
      point.

    Raises:
      Nothing
    '''

    # Catch the case that the fusepath is absolute (which it should be)
    if fusepath[0] == '/':
      rhs = fusepath[1:]
    else:
      rhs = fusepath

    transpath = os.path.join(tsumufs.cachePoint, rhs)
    return transpath

  def _isCachedToDisk(self, fusepath):
    '''
    Check to see if the file referenced by fusepath is cached to
    disk.

    Fusepath is expected to be an absolute path into the filesystem from
    the view seen from FUSE. Ie: all "absolute paths" are actually
    relative to the tsumufs mountpoint root.

    Returns:
      Boolean. True if the file is cached. False otherwise.

    Raises:
      OSError if there was an issue statting the file in question.
    '''

    # Lock the file for access
    self._lockFile(fusepath)

    try:
      try:
        statgoo = os.lstat(self._cachePathOf(fusepath))

        if stat.S_ISDIR(statgoo.st_mode) and tsumufs.nfsAvailable.isSet():
          return self._cachedDirents.has_key(fusepath)
      except OSError, e:
        if e.errno == errno.ENOENT:
          return False
        else:
          self._debug('_isCachedToDisk: Caught OSError: errno %d: %s'
                      % (e.errno, e.strerror))
          raise
      else:
        return True
    finally:
      self._unlockFile(fusepath)

  def _lockFile(self, fusepath):
    '''
    Lock the file for access exclusively.

    This prevents multiple FUSE threads from clobbering
    one-another. Note that this method blocks until a
    previously-locked file is unlocked.

    Returns:
      None

    Raises:
      None
    '''

#    tb = self._getCaller()
#     self._debug('Locking file %s (from: %s(%d): in %s).'
#                 % (fusepath, tb[0], tb[1], tb[2]))

    try:
      self._fileLocks[fusepath].acquire()
    except KeyError:
      lock = threading.RLock()
      lock.acquire()

      self._fileLocks[fusepath] = lock

  def _unlockFile(self, fusepath):
    '''
    Unlock the file for access.

    The inverse of lockFile. Releases a lock if one had been
    previously acquired.

    Returns:
      None

    Raises:
      None
    '''

#    tb = self._getCaller()
#     self._debug('Unlocking file %s (from: %s(%d): in %s).'
#                 % (fusepath, tb[0], tb[1], tb[2]))

    self._fileLocks[fusepath].release()
