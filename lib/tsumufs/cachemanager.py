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

  _cachedFiles = {}        # A hash of paths to unix timestamps of
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
          sys.exit(1)

      elif e.errno == errno.EACCES:
        self._debug('Cache point %s is unavailable: %s (exiting)'
                    % (tsumufs.cachePoint,
                       os.strerror(e.errno)))
        sys.exit(1)

  def isFileCached(self, path):
    '''
    Check to see if the file referenced by path is actually cached.

    Path is expected to be an absolute path into the filesystem from
    the view seen from FUSE. Ie: all "absolute paths" are actually
    relative to the tsumufs mountpoint root.

    Returns:
      Boolean. True if the file is cached. False otherwise.

    Raises:
      OSError if there was an issue statting the file in question.
    '''

    # Lock the file for access
    self.lockFile(path)

    if (self._cachedFiles.has_key(path) and
        self._cachedFiles[path]['type'] != 'stat'):
      self.unlockFile(path)
      return True

    try:
      try:
        self.statFile(path)
      except OSError, e:
        if e.errno == errno.ENOENT:
          if self._cachedFiles.has_key(path):
            del self._cachedFiles[path]
            return False
        else:
          self._debug('isFileCached: Caught OSError: errno %d: %s'
                      % (e.errno, e.strerror))
          self.unlockFile(path)
          raise
      else:
        return True
    finally:
      self.unlockFile(path)

  def statFile(self, path):
    '''
    Cache the stat referenced by path.

    This method locks the file for reading, returns the stat result
    (as returned by lstat()), enters the stat entry into the cache,
    and unlocks the file.
    '''

    # TODO: Make this update the inode -> file mappings.

    self.lockFile(path)

    nfsfilename   = '%s/%s' % (tsumufs.nfsMountPoint, path)

    # Bail out early if we've not cached the file and NFS is
    # unavailable. Simply unlock and return ENOENT.

    if not tsumufs.nfsAvailable.isSet():
      if not self._cachedFiles.has_key(path):
        self._debug('NFS unavailable and file not cached. Raising ENOENT.')
        self.unlockFile(path)
        raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))

    # Check to see if the file has been cached. If cached, and stat
    # has timed out, re-cache stat from nfs if available. Return the
    # cached stat.

    if self._cachedFiles.has_key(path):
      self._debug('Stat cache available for %s.' % path)

      if ((time.time() - self._cachedFiles[path]['timestamp']) >
          self._statTimeout):
        self._debug('Stat cache timeout occurred for %s (%d).' %
                    (path,
                     time.time() - self._cachedFiles[path]['timestamp']))

        if self._cachedFiles[path]['type'] == 'file':
          stat = os.lstat(nfsfilename)

          if self._cachedFiles[path]['stat'] != stat:
            # TODO: Schedule this file for reintegration or update of
            # the full cached copy.
            pass

          self._cachedFiles[path]['timestamp'] = time.time()
          self._cachedFiles[path]['stat'] = stat

        elif self._cachedFiles[path]['type'] == 'dir':
          stat = os.lstat(nfsfilename)

          if self._cachedFiles[path]['stat'] != stat:
            # TODO: Should maybe update the dir's dirents here?
            pass

          self._cachedFiles[path]['timestamp'] = time.time()
          self._cachedFiles[path]['stat'] = stat

        elif self._cachedFiles[path]['type'] == 'stat':
          # Just an ordinary stat cache.

          self._cachedFiles[path]['timestamp'] = time.time()
          self._cachedFiles[path]['stat'] = os.lstat(nfsfilename)


        self._debug('Stat cache acquired: %s' %
                    (str(self._cachedFiles[path]['stat'])))
    else:
      self._debug('No stat cache for %s available. Caching stat.' % path)

      try:
        # Create a new stat cached entry
        self._cachedFiles[path] = {
          'type': 'stat',
          'stat': os.lstat(nfsfilename),
          'timestamp': time.time()
          }
      except:
        self.unlockFile(path)
        raise

    self.unlockFile(path)
    return self._cachedFiles[path]['stat']

  def getDirents(self, path):
    '''
    Return the dirents from a directory's contents if cached.
    '''

    self.lockFile(path)

    nfsfilename   = '%s/%s' % (tsumufs.nfsMountPoint, path)

    # Bail out early if we've not cached the file and NFS is
    # unavailable. Simply unlock and return ENOENT.

    if not tsumufs.nfsAvailable.isSet():
      if not self._cachedFiles.has_key(path):
        self._debug('NFS not available, and %s not cached -- raising ENOENT.'
                    % path)
        self.unlockFile(path)
        raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))

    # Check to see if the file has been cached. If cached, and stat
    # has timed out, re-cache stat from nfs if available. Return the
    # cached dirents.

    if (self._cachedFiles.has_key(path) and
        (self._cachedFiles[path]['type'] == 'dir')):
      if ((time.time() - self._cachedFiles[path]['timestamp']) >
          self._statTimeout):
        self._cachedFiles[path]['timestamp'] = time.time()
        self._cachedFiles[path]['stat'] = os.lstat(nfsfilename)
        self._cachedFiles[path]['dirents'] = ([ '.', '..' ] +
                                              os.listdir(nfsfilename))
    else:
      if os.path.isdir(nfsfilename):
        self._debug('Dirents not cached -- caching %s.' % path)
        self.cacheDir(path)
      else:
        self._debug(('Path %s is not a directory (os.path.isdir()'
                     'reports false') % path)
        self.unlockFile(path)
        raise OSError(errno.ENOTDIR, os.strerror(errno.ENOTDIR))

    self.unlockFile(path)
    return self._cachedFiles[path]['dirents']

  def cacheDir(self, path):
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

    self.lockFile(path)

    nfsfilename   = '%s/%s' % (tsumufs.nfsMountPoint, path)
    cachefilename = '%s/%s' % (tsumufs.cachePoint, path)

    try:
      try:
        stat = os.lstat(nfsfilename)

        if (self.shouldCacheFile(path) and
            (path != '/')):
          self._debug('Caching directory %s to disk.' % path)

          try:
            os.mkdir(cachefilename)
            shutil.copystat(nfsfilename, cachefilename)
            os.chown(cachefilename, stat.st_uid, stat.st_gid)
          except OSError, e:
            if e.errno == errno.EEXIST:
              self._debug('Dir %s already cached.' % path)
            else:
              raise

        self._cachedFiles[path] = {
          'type': 'dir',
          'timestamp': time.time(),
          'dirents': ([ '.', '..' ] + os.listdir(nfsfilename)),
          'stat': stat
          }
      except OSError, e:
        self._debug('cacheDir: caught OSError: errno %d: %s'
                    % (e.errno, e.strerror))
        raise
    finally:
      self.unlockFile(path)

  def cacheFile(self, path):
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
      None

    Raises:
      OSError if there was an issue attempting to copy the file
      across to cache.
    '''

    nfsfilename   = '%s/%s' % (tsumufs.nfsMountPoint, path)
    cachefilename = '%s/%s' % (tsumufs.cachePoint, path)

    if not self.shouldCacheFile(path):
      return None

    self.lockFile(path)

    if (self._cachedFiles.has_key(path) and
        self._cachedFiles[path]['type'] == 'file'):
      if time.time() - self._cachedFiles[path]['timestamp'] <= self._statTimeout:
        self._debug('File cached and has not reached the stat timeout.')
        self.unlockFile(path)
        return None

    self._debug('Caching file %s to disk.' % path)

    try:
      try:
        timestamp = time.time()
        curstat = os.lstat(nfsfilename)

        if (not self._cachedFiles.has_key(path) or
            (curstat.st_blocks != self._cachedFiles[path]['stat'].st_blocks) or
            (curstat.st_mtime != self._cachedFiles[path]['stat'].st_mtime) or
            (curstat.st_size != self._cachedFiles[path]['stat'].st_size) or
            (curstat.st_ino != self._cachedFiles[path]['stat'].st_ino)):
          self._debug(('Data stat changed or file never cached '
                       'before. Recaching file.'))

          if (stat.S_ISREG(curstat.st_mode) or
              stat.S_ISLNK(curstat.st_mode)):
            shutil.copy2(nfsfilename, cachefilename)
            shutil.copystat(nfsfilename, cachefilename)
            os.chown(cachefilename, curstat.st_uid, curstat.st_gid)

            self._cachedFiles[path] = {
              'type': 'file',
              'timestamp': time.time(),
              'stat': curstat
              }
        else:
          self._debug('Data stat unchanged. Recaching metadata via stat().')

          self._cachedFiles[path]['timestamp'] = timestamp
          self._cachedFiles[path]['stat'] = curstat
      except OSError, e:
        self._debug('cacheFile: Caught OSError: errno %d: %s'
                    % (e.errno, e.strerror))
    finally:
      self.unlockFile(path)

  def removeCachedFile(self, path):
    '''
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
    '''

    self.lockFile(path)
    cachefilename = '%s/%s' % (tsumufs.cachePoint, path)

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
        self._debug('removeCachedFile: Caught OSError: errno %d: %s'
                    % (e.errno, e.strerror))

        if e.errno == errno.ENOENT:
          del self._cachedFiles[path]
        else:
          raise
    finally:
      self.unlockFile(path)

  def readFile(self, path, offset, length, mode):
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

    self.lockFile(path)

    if not self.isFileCached(path):
      if not tsumufs.nfsAvailable.isSet():
        self._debug(('NFS not available, and %s not cached '
                     '-- raising ENOENT.') % path)
        self.unlockFile(path)
        raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))
      else:
        if tsumufs.cacheManager.shouldCacheFile(path):
          self._debug(('File not cached to disk, but NFS '
                       'available. Caching file to disk.'))
          tsumufs.cacheManager.cacheFile(path)
          filepath = tsumufs.cachePoint + path
        else:
          # TODO: Make this use calls into NFSMount to read the NFS
          # side of things instead of just arbitrarily reading it out
          # ourselves.

          self._debug(('File not cached to disk and should not cache '
                       'to disk.'))
          filepath = tsumufs.nfsMountPoint + path
    else:
      self._debug(('File already fully cached to disk and should not cache '
                   'to disk again. Reading from cache.'))
      filepath = tsumufs.cachePoint + path

    try:
      try:
        self._debug('Reading file contents from %s' % filepath)

        fp = open(filepath, mode)
        fp.seek(offset)
        result = fp.read(length)
        fp.close()

        return result
      except OSError, e:
        self._debug('OSError caught: errno %d: %s'
                    % (e.errno, e.strerror))
        raise
    finally:
      self.unlockFile(path)

  def shouldCacheFile(self, path):
    '''
    Method to determine if a file referenced by path should be
    cached, as aoccording to the cachespec file.

    Note: Currently this method only returns True, and none of the
    cachespec information is actually processed or used.

    Returns:
      Boolean. True if the file should be cached.

    Raises:
      None
    '''

    return True

  def lockFile(self, path):
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

    tb = self._getCaller()
    self._debug('Locking file %s (from: %s(%d): in %s).'
                % (path, tb[0], tb[1], tb[2]))

    try:
      self._fileLocks[path].acquire()
    except KeyError:
      self._fileLocks[path] = threading.RLock()
      self._fileLocks[path].acquire()

  def unlockFile(self, path):
    '''
    Unlock the file for access.

    The inverse of lockFile. Releases a lock if one had been
    previously acquired.

    Returns:
      None

    Raises:
      None
    '''

    tb = self._getCaller()
    self._debug('Unlocking file %s (from: %s(%d): in %s).'
                % (path, tb[0], tb[1], tb[2]))

    self._fileLocks[path].release()
