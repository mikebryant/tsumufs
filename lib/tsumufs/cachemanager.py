# Copyright (C) 2008  Google, Inc. All Rights Reserved.
# Copyright (C) 2012  Michael Bryant.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

'''TsumuFS, a NFS-based caching filesystem.'''

import os
import os.path
import sys
import shutil
import errno
import stat
import thread
import threading
import time
import random

import logging
logger = logging.getLogger(__name__)

import tsumufs
from extendedattributes import extendedattribute


class CacheManager(object):
  '''
  Class designed to handle management of the cache. All caching
  operations (and decaching operations) are performed here.
  '''

  _statTimeout = 60        # The number of seconds we use the cached
                           # copy's stat information for before we
                           # attempt to update it from the nfs mount.  This is
                           # altered by fuzzing the value plus/minus 10
                           # seconds, to help reduce entire directory stat
                           # timeouts.

  _cachedStats = {}        # A hash of paths to stat entries and last stat
                           # times.  This is used to reduce the number of stats
                           # called on NFS primarily.

  _cachedDirents = {}      # A hash of paths to unix timestamps of
                           # when we last cached the file.

  _fileLocks = {}          # A hash of paths to locks to serialize
                           # access to files in the cache.

  _cacheSpec = {}          # A hash of paths to bools to remember the policy of
                           # whether files or parent directories (recursively)

  def __init__(self):
    # Install our custom exception handler so that any exceptions are
    # output to the syslog rather than to /dev/null.
    sys.excepthook = tsumufs.syslogExceptHook

    try:
      os.stat(tsumufs.cachePoint)
    except OSError, e:
      if e.errno == errno.ENOENT:
        logging.debug('Cache point %s was not found -- creating'
                    % tsumufs.cachePoint)

        try:
          pathparts = tsumufs.cachePoint.split('/')
          path = '/'

          for pathpart in pathparts:
            if pathpart == '':
              continue

            path = os.path.join(path, pathpart)

            if not os.path.exists(path):
              logging.debug('Path %s doesn\'t exist -- creating.' % path)
              os.mkdir(path)
        except OSError, e:
          logger.debug('Unable to create cache point: %s (exiting)'
                      % os.strerror(e.errno))
          raise e

      elif e.errno == errno.EACCES:
        logger.debug('Cache point %s is unavailable: %s (exiting)'
                    % (tsumufs.cachePoint,
                       os.strerror(e.errno)))
        raise e

  def _cacheStat(self, realpath):
    '''
    Stat a file, or return the cached stat of that file.

    This method functions nearly exactly the same as os.lstat(), except it
    returns a cached copy if the last time we cached the stat wasn't longer than
    the _statTimeout set above.

    Returns:
      posix.stat_result

    Raises:
      OSError if there was a problem reading the stat.
    '''

    recache = False

    if not self._cachedStats.has_key(realpath):
      logger.debug('Stat never cached.')
      recache = True

    elif (time.time() - self._cachedStats[realpath]['time']
          > self._statTimeout):
      logger.debug('Stat cache timeout.')
      recache = True

    else:
      logger.debug('Using cached stat.')

    if recache:
      logging.debug('Caching stat.')

      # TODO(jtg): detect mount failures here
      stat_result = os.lstat(realpath)

      self._cachedStats[realpath] = {
        'stat': stat_result,
        'time': time.time() + (random.random() * 20 - 10)
        }

    return self._cachedStats[realpath]['stat']

  def _invalidateStatCache(self, realpath):
    '''
    Unconditionally invalidate the cached stat of a file.

    Returns:
      None

    Raises:
      Nothing
    '''

    if self._cachedStats.has_key(realpath):
      del self._cachedStats[realpath]

  def _invalidateDirentCache(self, dirname, basename):
    '''
    Unconditionally invalidate a dirent for a file.

    Returns:
      None

    Raises:
      Nothing
    '''

    if self._cachedDirents.has_key(dirname):
      if basename in self._cachedDirents[dirname]:
        logger.debug('Removing %s from the dirent cache.' %
                    os.path.join(dirname, basename))

        while basename in self._cachedDirents[dirname]:
          self._cachedDirents[dirname].remove(basename)

  def _checkForNFSDisconnect(self, exception, opcodes):
    '''
    '''

    if 'use-nfs' in opcodes:
      if exception.errno in (errno.EIO, errno.ESTALE):
        logger.debug(('Caught errno %s; NFS invalid -- entering disconnected '
                     'mode.') %
                    errno.errorcode[exception.errno])

        tsumufs.nfsMount.unmount()
        tsumufs.nfsAvailable.clear()

  def statFile(self, fusepath):
    '''
    Return the stat referenced by fusepath.

    This method locks the file for reading, returns the stat result
    and unlocks the file.

    Returns:
      posix.stat_result

    Raises:
      OSError if there was a problemg getting the stat.
    '''

    self.lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath, for_stat=True)
      logger.debug('Opcodes are: %s' % str(opcodes))

      self._validateCache(fusepath, opcodes)
      realpath = self._generatePath(fusepath, opcodes)

      if 'enoent' in opcodes:
        raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))

      try:
        logger.debug('Statting %s' % realpath)

        if 'use-nfs' in opcodes:
          result = self._cacheStat(realpath)
          tsumufs.NameToInodeMap.setNameToInode(realpath, result.st_ino)

          return result
        else:
          # Special case the root of the mount.
          if os.path.abspath(fusepath) == '/':
            return os.lstat(realpath)

          perms = tsumufs.permsOverlay.getPerms(fusepath)
          perms = perms.overlayStatFromFile(realpath)
          logger.debug('Returning %s as perms.' % repr(perms))

          return perms

      except OSError, e:
        self._checkForNFSDisconnect(e, opcodes)
        raise

    finally:
      self.unlockFile(fusepath)

  def fakeOpen(self, fusepath, flags, uid=None, gid=None, mode=None):
    '''
    Attempt to open a file on the local disk.

    Returns:
      None

    Raises:
      OSError on problems opening the file.
    '''

    # Several things to worry about here:
    #
    # In normal open cases where we just want to open the file and not create
    # it, we can just assume the normal read routines, and open from cache if
    # possible.
    #
    # Flags that will give us trouble:
    #
    #   O_CREAT            - Open and create if not there already, no error if
    #                        exists.
    #
    #   O_CREAT | O_EXCL   - Open, create, and error out if the file exists or
    #                        if the path contains a symlink. Error used is
    #                        EEXIST.
    #
    #   O_TRUNC            - Open an existing file, truncate the contents.
    #

    self.lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)

      if flags & os.O_CREAT:
        if 'enoent' in opcodes:
          logger.debug('O_CREAT and enoent in opcodes. Mogrifying.')
          opcodes.remove('enoent')
          if 'use-nfs' in opcodes:
            opcodes.remove('use-nfs')
          opcodes.append('use-cache')
          logger.debug('Opcodes are now %s' % opcodes)

      try:
        self._validateCache(fusepath, opcodes)
      except OSError, e:
        if e.errno != errno.ENOENT:
          raise

        if flags & os.O_CREAT:
          logger.debug('Skipping over ENOENT since we want O_CREAT')
          pass
        else:
          logger.debug('Couldn\'t find %s -- raising ENOENT' % fusepath)
          raise

      realpath = self._generatePath(fusepath, opcodes)
      logger.debug('Attempting open of %s.' % realpath)

      if 'use-cache' in opcodes:
        logger.debug('Told to use the cache.')

        if flags & os.O_CREAT:
          dirname = os.path.dirname(fusepath)
          basename = os.path.basename(fusepath)

          if self._cachedDirents.has_key(dirname):
            if not basename in self._cachedDirents[dirname]:
              logger.debug('Inserting new file into the cached dirents for the '
                          'parent directory.')
              self._cachedDirents[dirname].append(basename)

          # TODO(jtg): Add in the new permissions into the overlay

        if flags & os.O_TRUNC:
          # Invalidate the stat cache if one exists.
          logger.debug('Invalidating stat cache')
          self._invalidateStatCache(realpath)

      try:
        logging.debug('Opening file')
        if mode:
          fd = os.open(realpath, flags, tsumufs.defaultCacheMode)
        else:
          fd = os.open(realpath, flags)

        # TODO(jtg): Store permissions here
        logger.debug('Storing new permissions')

      except OSError, e:
        self._checkForNFSDisconnect(e, opcodes)
        raise

      logger.debug('Closing file.')
      os.close(fd)

    finally:
      logger.debug('Unlocking file.')
      self.unlockFile(fusepath)
      logger.debug('Method complete.')

  def getDirents(self, fusepath):
    '''
    Return the dirents from a directory's contents if cached.
    '''

    self.lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)
      self._validateCache(fusepath, opcodes)

      if 'enoent' in opcodes:
        raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))

      if tsumufs.nfsAvailable.isSet():
        logger.debug('NFS is available -- combined dirents from NFS and '
                    'cached disk.')

        nfs_dirents = set(self._cachedDirents[fusepath])
        cached_dirents = set(os.listdir(tsumufs.cachePathOf(fusepath)))
        final_dirents_list = [ '.', '..' ]

        for dirent in nfs_dirents.union(cached_dirents):
          final_dirents_list.append(dirent)

        logger.debug('nfs_dirents = %s' % nfs_dirents);
        logger.debug('cached_dirents = %s' % cached_dirents);
        logger.debug('final_dirents_list = %s' % final_dirents_list);

        return final_dirents_list

      else:
        logger.debug('NFS is unavailable -- returning cached disk dir stuff.')

        dirents = [ '.', '..' ]
        dirents.extend(os.listdir(tsumufs.cachePathOf(fusepath)))

        return dirents

    finally:
      self.unlockFile(fusepath)

  def _flagsToStdioMode(self, flags):
    '''
    Convert flags to stupidio's mode.
    '''

    if flags & os.O_RDWR:
      if flags & os.O_APPEND:
        result = 'a+'
      else:
        result = 'w+'

    elif flags & os.O_WRONLY:
      if flags & os.O_APPEND:
        result = 'a'
      else:
        result = 'w'

    else: # O_RDONLY
      result = 'r'

    return result

  def readFile(self, fusepath, offset, length, flags, mode=None):
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

    self.lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)
      self._validateCache(fusepath, opcodes)
      realpath = self._generatePath(fusepath, opcodes)

      logger.debug('Reading file contents from %s [ofs: %d, len: %d]'
                  % (realpath, offset, length))

      # TODO(jtg): Validate permissions here

      if mode != None:
        fd = os.open(realpath, flags, mode)
      else:
        fd = os.open(realpath, flags)

      fp = os.fdopen(fd, self._flagsToStdioMode(flags))
      fp.seek(0)
      fp.seek(offset)
      result = fp.read(length)
      fp.close()

      logger.debug('Read %s' % repr(result))
      return result

    finally:
      self.unlockFile(fusepath)

  def writeFile(self, fusepath, offset, buf, flags, mode=None):
    '''
    Write a chunk of data to the file referred to by fusepath.

    This method acts very much like the typical idiom:

      fp = open(file, mode)
      fp.seek(offset)
      result = fp.write(buf)
      return result

    Except that all writes go diractly to the cache first, and a synclog entry
    is created.

    Returns:
      The number of bytes written.

    Raises:
      OSError on error writing the data.
      IOError on error writing the data.
    '''

    self.lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)
      self._validateCache(fusepath, opcodes)
      realpath = tsumufs.cachePathOf(fusepath)

      logger.debug('Writing to file %s at offset %d with buffer length of %d '
                  'and mode %s' % (realpath, offset, len(buf), mode))

      # TODO(jtg): Validate permissions here, too

      if mode != None:
        fd = os.open(realpath, flags, mode)
      else:
        fd = os.open(realpath, flags)

      fp = os.fdopen(fd, self._flagsToStdioMode(flags))

      if offset >= 0:
        fp.seek(offset)
      else:
        fp.seek(0, 2)

      bytes_written = fp.write(buf)
      fp.close()

      # Since we wrote to the file, invalidate the stat cache if it exists.
      self._invalidateStatCache(realpath)

      return bytes_written
    finally:
      self.unlockFile(fusepath)

  def readLink(self, fusepath):
    '''
    Return the target of a symlink.
    '''

    self.lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)
      self._validateCache(fusepath, opcodes)
      realpath = self._generatePath(fusepath, opcodes)

      logging.debug('Reading link from %s' % realpath)

      return os.readlink(realpath)
    finally:
      self.unlockFile(fusepath)

  def makeSymlink(self, fusepath, target):
    '''
    Create a new symlink with the target specified.

    Returns:
      None

    Raises:
      OSError, IOError
    '''

    self.lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)

      # Skip enoents -- we're creating a file.
      try:
        self._validateCache(fusepath, opcodes)
      except (IOError, OSError), e:
        if e.errno != errno.ENOENT:
          raise

      realpath = self._generatePath(fusepath, opcodes)
      dirname = os.path.dirname(fusepath)
      basename = os.path.basename(fusepath)

      if 'use-cache' in opcodes:
        if self._cachedDirents.has_key(dirname):
          self._cachedDirents[dirname].append(basename)

      self._invalidateStatCache(realpath)

      # TODO(permissions): make this use the permissions overlay
      return os.symlink(realpath, target)

    finally:
      self.unlockFile(fusepath)

  def makeDir(self, fusepath):
    self.lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)

      # Skip enoents -- we're creating a dir.
      try:
        self._validateCache(fusepath, opcodes)
      except (IOError, OSError), e:
        if e.errno != errno.ENOENT:
          raise

      realpath = tsumufs.cachePathOf(fusepath)
      dirname  = os.path.dirname(fusepath)
      basename = os.path.basename(fusepath)

      if 'use-cache' in opcodes:
        if self._cachedDirents.has_key(dirname):
          self._cachedDirents[dirname].append(basename)

      self._cachedDirents[fusepath] = []
      self._invalidateStatCache(realpath)

      logging.debug("Making directory %s" % realpath)
      return os.mkdir(realpath, 0755)

    finally:
      self.unlockFile(fusepath)

  def chmod(self, fusepath, mode):
    '''
    Chmod a file.

    Returns:
      None

    Raises:
      OSError, IOError
    '''

    self.lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)
      self._validateCache(fusepath, opcodes)
      realpath = self._generatePath(fusepath, opcodes)

      try:
        perms = tsumufs.permsOverlay.getPerms(fusepath)
      except KeyError:
        statgoo = self.statFile(fusepath)
        perms = { 'uid': statgoo.st_uid,
                  'gid': statgoo.st_gid,
                  'mode': statgoo.st_mode }

      perms.mode = (perms.mode & 070000) | mode
      tsumufs.permsOverlay.setPerms(fusepath, perms.uid, perms.gid, perms.mode)

      self._invalidateStatCache(tsumufs.nfsPathOf(fusepath))
    finally:
      self.unlockFile(fusepath)

  def chown(self, fusepath, uid, gid):
    '''
    Chown a file.

    Returns:
      None

    Raises:
      OSError, IOError
    '''

    self.lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)
      self._validateCache(fusepath, opcodes)
      realpath = self._generatePath(fusepath, opcodes)

      # TODO(permissions): Fix this to use the PermissionsOverlay

      return os.chown(fusepath, uid, gid)
    finally:
      self.unlockFile(fusepath)

  def rename(self, fusepath, newpath):
    '''
    Rename a file.

    Returns:
      None

    Raises:
      OSError, IOError
    '''

    self.lockFile(fusepath)
    self.lockFile(newpath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)
      self._validateCache(fusepath, opcodes)

      try:
        opcodes = self._genCacheOpcodes(newpath)
        self._validateCache(newpath, opcodes)

      except OSError, e:
        if e.errno == errno.ENOENT:
          logging.debug('Squelching an ENOENT -- this is for rename.')
        else:
          raise

      srcpath = self._generatePath(fusepath, opcodes)
      destpath = self._generatePath(newpath, opcodes)

      logging.debug('Renaming %s (%s) -> %s (%s)' % (fusepath, srcpath,
                                                   newpath, destpath))

      # Don't need to do anything with the perms, because the inode stays the
      # same during a rename. We're just passing around the reference between
      # directory hashes.

      result = os.rename(srcpath, destpath)

      # Invalidate the dirent cache for the old pathname
      self._invalidateDirentCache(os.path.dirname(fusepath),
                                  os.path.basename(fusepath))

      return result
    finally:
      self.unlockFile(fusepath)
      self.unlockFile(newpath)

  def access(self, uid, fusepath, mode):
    '''
    Test for access to a path.

    Returns:
      True upon successful check, otherwise False. Don't alter _recurse. That's
      used internally.

    Raises:
      OSError upon access problems.
    '''

    self.lockFile(fusepath)

    try:
      opcodes = self._genCacheOpcodes(fusepath)
      self._validateCache(fusepath, opcodes)
      realpath = self._generatePath(fusepath, opcodes)

      if 'use-nfs' in opcodes:
        logging.debug('Using nfs for access')
        return os.access(realpath, mode)

      # TODO(cleanup): make the above chunk of code into a decorator for crying
      # out loud. We do this in every public method and it adds confusion. =o(

      # Root owns everything
      if uid == 0:
        logging.debug('Root -- returning 0')
        return 0

      # Recursively go down the path from longest to shortest, checking access
      # perms on each directory as we go down.
      if fusepath != '/':
        self.access(uid,
                    os.path.dirname(fusepath),
                    os.X_OK)

      file_stat = self.statFile(fusepath)

      mode_string = ''
      if mode & os.R_OK:
        mode_string += 'R_OK|'
      if mode & os.W_OK:
        mode_string += 'W_OK|'
      if mode & os.X_OK:
        mode_string += 'X_OK|'
      if mode == os.F_OK:
        mode_string = 'F_OK|'
      mode_string = mode_string[:-1]

      logging.debug('access(%s, %s) -> (uid, gid, mode) = (%d, %d, %o)' %
                  (repr(fusepath), mode_string,
                   file_stat.st_uid, file_stat.st_gid, file_stat.st_mode))

      # Catch the case where the user only wants to check if the file exists.
      if mode == os.F_OK:
        logging.debug('User just wanted to verify %s existed -- returning 0.' %
                    fusepath)
        return 0

      # Check user bits first
      if uid == file_stat.st_uid:
        if ((file_stat.st_mode & stat.S_IRWXU) >> 6) & mode:
          logging.debug('Allowing for user bits.')
          return 0

      # Then group bits
      if file_stat.st_gid in tsumufs.getGidsForUid(uid):
        if ((file_stat.st_mode & stat.S_IRWXG) >> 3) & mode:
          logging.debug('Allowing for group bits.')
          return 0

      # Finally assume other bits
      if (file_stat.st_mode & stat.S_IRWXO) & mode:
        logging.debug('Allowing for other bits.')
        return 0

      logging.debug('No access allowed.')
      raise OSError(errno.EACCES, os.strerror(errno.EACCES))

    finally:
      self.unlockFile(fusepath)

  def truncateFile(self, fusepath, size):
    '''
    Unconditionally truncate the file. Don't check to see if the user has
    access.
    '''

    try:
      self.lockFile(fusepath)

      opcodes = self._genCacheOpcodes(fusepath)
      self._validateCache(fusepath, opcodes)
      realpath = self._generatePath(fusepath, opcodes)

      logging.debug('Truncating %s to %d bytes.' % (realpath, size))

      fd = os.open(realpath, os.O_RDWR)
      os.ftruncate(fd, size)
      os.close(fd)

      # Since we wrote to the file, invalidate the stat cache if it exists.
      self._invalidateStatCache(realpath)

      return 0

    finally:
      self.unlockFile(fusepath)

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

    self.lockFile(fusepath)

    try:
      nfspath   = tsumufs.nfsPathOf(fusepath)
      cachepath = tsumufs.cachePathOf(fusepath)
      stat      = os.lstat(nfspath)

      logging.debug('nfspath = %s' % nfspath)
      logging.debug('cachepath = %s' % cachepath)

      if fusepath == '/':
        logging.debug('Asking to cache root -- skipping the cache to '
                    'disk operation, but caching data in memory.')
      else:
        try:
          os.mkdir(cachepath)
        except OSError, e:
          # Skip EEXIST errors -- if it already exists, it may have files in it
          # already. Simply copy the stat and chown it again, then cache the
          # listdir operation as well.

          if e.errno != errno.EEXIST:
            raise

        shutil.copystat(nfspath, cachepath)

        tsumufs.permsOverlay.setPerms(fusepath,
                                      stat.st_uid,
                                      stat.st_gid,
                                      stat.st_mode)

      logging.debug('Caching directory %s to disk.' % fusepath)
      self._cachedDirents[fusepath] = os.listdir(nfspath)

    finally:
      self.unlockFile(fusepath)

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

    # TODO(jtg): Add support for storing the UID/GID

    self.lockFile(fusepath)

    try:
      logging.debug('Caching file %s to disk.' % fusepath)

      nfspath = tsumufs.nfsPathOf(fusepath)
      cachepath = tsumufs.cachePathOf(fusepath)

      curstat = os.lstat(nfspath)

      if (stat.S_ISREG(curstat.st_mode) or
          stat.S_ISFIFO(curstat.st_mode) or
          stat.S_ISSOCK(curstat.st_mode) or
          stat.S_ISCHR(curstat.st_mode) or
          stat.S_ISBLK(curstat.st_mode)):

        shutil.copy(nfspath, cachepath)
        shutil.copystat(nfspath, cachepath)

      elif stat.S_ISLNK(curstat.st_mode):
        dest = os.readlink(nfspath)

        try:
          os.unlink(cachepath)
        except OSError, e:
          if e.errno != errno.ENOENT:
            raise

        os.symlink(dest, cachepath)
        #os.lchown(cachepath, curstat.st_uid, curstat.st_gid)
        #os.lutimes(cachepath, (curstat.st_atime, curstat.st_mtime))
      elif stat.S_ISDIR(curstat.st_mode):
        # Caching a directory to disk -- call cacheDir instead.
        logging.debug('Request to cache a directory -- calling _cacheDir')
        self._cacheDir(fusepath)

      tsumufs.permsOverlay.setPerms(fusepath,
                                    curstat.st_uid,
                                    curstat.st_gid,
                                    curstat.st_mode)
    finally:
      self.unlockFile(fusepath)

  def removeCachedFile(self, fusepath):
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

    self.lockFile(fusepath)

    try:
      cachefilename = tsumufs.cachePathOf(fusepath)
      ino = os.lstat(cachefilename).st_ino

      if os.path.isfile(cachefilename) or os.path.islink(cachefilename):
        os.unlink(cachefilename)
      elif os.path.isdir(cachefilename):
        os.rmdir(cachefilename)

      # Invalidate the stat cache for this file
      self._invalidateStatCache(cachefilename)

      # Remove this file from the dirent cache if it was put in there.
      self._invalidateDirentCache(os.path.dirname(fusepath),
                                  os.path.basename(fusepath))

      # Remove this file from the permsOverlay
      tsumufs.permsOverlay.removePerms(ino)

    finally:
      self.unlockFile(fusepath)

  def _shouldCacheFile(self, fusepath):
    '''
    Method to determine if a file referenced by fusepath should be
    cached, as aoccording to the cachespec.

    Note: If a file is not explicitly listed, but any parent directory
    above the file is, the policy is inherited.

    Returns:
      Boolean. True if the file should be cached.

    Raises:
      None
    '''

    # special case
    if fusepath == "/":
      return True

    path = fusepath
    while path != "/":
      if self._cacheSpec.has_key(path):
        logging.debug('caching of %s is %s because of policy on %s' % (
                    fusepath, self._cacheSpec[path], path))
        return self._cacheSpec[path]
      # not found explicity, so inherit policy from parent dir
      (path, base) = os.path.split(path)

    # return default policy
    logging.debug('default caching policy on %s' % fusepath)
    if tsumufs.syncLog.isUnlinkedFile(fusepath):
      return False
    else:
      return True

  def _validateCache(self, fusepath, opcodes=None):
    '''
    Validate that the cached copies of fusepath on local disk are the same as
    the copies upstream, based upon the opcodes geenrated by _genCacheOpcodes.

    Returns:
      None

    Raises:
      Nothing
    '''

    if opcodes == None:
      opcodes = self._genCacheOpcodes(fusepath)

    logging.debug('Opcodes are: %s' % opcodes)

    for opcode in opcodes:
      if opcode == 'remove-cache':
        logging.debug('Removing cached file %s' % fusepath)
        self.removeCachedFile(fusepath)
      if opcode == 'cache-file':
        logging.debug('Updating cache of file %s' % fusepath)
        self._cacheFile(fusepath)
      if opcode == 'merge-conflict':
        # TODO: handle a merge-conflict?
        logging.debug('Merge/conflict on %s' % fusepath)

  def _generatePath(self, fusepath, opcodes=None):
    '''
    Return the path to use for all file operations, based upon the current state
    of the world generated by _genCacheOpcodes.

    Returns:
      None

    Raises:
      Nothing
    '''

    if opcodes == None:
      opcodes = self._genCacheOpcodes(fusepath)

    logging.debug('Opcodes are: %s' % opcodes)

    for opcode in opcodes:
      if opcode == 'enoent':
        logging.debug('ENOENT on %s' % fusepath)
        raise OSError(errno.ENOENT, os.strerror(errno.ENOENT))
      if opcode == 'use-nfs':
        logging.debug('Returning nfs path for %s' % fusepath)
        return tsumufs.nfsPathOf(fusepath)
      if opcode == 'use-cache':
        logging.debug('Returning cache path for %s' % fusepath)
        return tsumufs.cachePathOf(fusepath)

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

    # do the test below exactly once to improve performance, reduce
    # a few minor race conditions and to improve readability
    isCached = self.isCachedToDisk(fusepath)
    shouldCache = self._shouldCacheFile(fusepath)
    nfsAvail = tsumufs.nfsAvailable.isSet()

    # if not cachedFile and not nfsAvailable raise -ENOENT
    if not isCached and not nfsAvail:
      logging.debug('File not cached, no nfs -- enoent')
      return ['enoent']

    # if not cachedFile and not shouldCache
    if not isCached and not shouldCache:
      if nfsAvail:
        if tsumufs.syncLog.isUnlinkedFile(fusepath):
          logging.debug('File previously unlinked -- returning use cache.')
          return ['use-cache']
        else:
          logging.debug('File not cached, should not cache -- use nfs.')
          return ['use-nfs']

    # if not cachedFile and     shouldCache
    if not isCached and shouldCache:
      if nfsAvail:
        if for_stat:
          logging.debug('Returning use-nfs, as this is for stat.')
          return ['use-nfs']

        logging.debug(('File not cached, should cache, nfs avail '
                     '-- cache file, use cache.'))
        return ['cache-file', 'use-cache']
      else:
        logging.debug('File not cached, should cache, no nfs -- enoent')
        return ['enoent']

    # if     cachedFile and not shouldCache
    if isCached and not shouldCache:
      if nfsAvail:
        logging.debug(('File cached, should not cache, nfs avail '
                     '-- remove cache, use nfs'))
        return ['remove-cache', 'use-nfs']
      else:
        logging.debug(('File cached, should not cache, no nfs '
                     '-- remove cache, enoent'))
        return ['remove-cache', 'enoent']

    # if     cachedFile and     shouldCache
    if isCached and shouldCache:
      if nfsAvail:
        if self._nfsDataChanged(fusepath):
          if tsumufs.syncLog.isFileDirty(fusepath):
            logging.debug('Merge conflict detected.')
            return ['merge-conflict']
          else:
            if for_stat:
              logging.debug('Returning use-nfs, as this is for stat.')
              return ['use-nfs']

            logging.debug(('Cached, should cache, nfs avail, nfs changed, '
                         'cache clean -- recache, use cache'))
            return ['cache-file', 'use-cache']

    logging.debug('Using cache by default, as no other cases matched.')
    return ['use-cache']

  def _nfsDataChanged(self, fusepath):
    '''
    Check to see if the NFS data has changed since our last stat.

    Returns:
      Boolean true or false.

    Raises:
      Any error that might occur during an os.lstat(), aside from ENOENT.
    '''

    self.lockFile(fusepath)

    try:
      try:
        cachedstat = self._cachedStats[fusepath]['stat']
        realstat   = os.lstat(tsumufs.nfsPathOf(fusepath))

        if ((cachedstat.st_blocks != realstat.st_blocks) or
            (cachedstat.st_mtime != realstat.st_mtime) or
            (cachedstat.st_size != realstat.st_size) or
            (cachedstat.st_ino != realstat.st_ino)):
          return True
        else:
          return False

      except OSError, e:
        if e.errno == errno.ENOENT:
          return False
        else:
          raise

      except KeyError, e:
        return False

    finally:
      self.unlockFile(fusepath)

  def isCachedToDisk(self, fusepath):
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
    self.lockFile(fusepath)

    try:
      try:
        statgoo = os.lstat(tsumufs.cachePathOf(fusepath))

        if stat.S_ISDIR(statgoo.st_mode) and tsumufs.nfsAvailable.isSet():
          return self._cachedDirents.has_key(fusepath)
      except OSError, e:
        if e.errno == errno.ENOENT:
          return False
        else:
          logging.debug('_isCachedToDisk: Caught OSError: errno %d: %s'
                      % (e.errno, e.strerror))
          raise
      else:
        return True
    finally:
      self.unlockFile(fusepath)

  def lockFile(self, fusepath):
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

#     tb = self._getCaller()
#     logging.debug('Locking file %s (from: %s(%d): in %s <%d>).'
#                 % (fusepath, tb[0], tb[1], tb[2], thread.get_ident()))

    try:
      lock = self._fileLocks[fusepath]
    except KeyError:
      lock = self._fileLocks.setdefault(fusepath, threading.RLock())

    lock.acquire()

  def unlockFile(self, fusepath):
    '''
    Unlock the file for access.

    The inverse of lockFile. Releases a lock if one had been
    previously acquired.

    Returns:
      None

    Raises:
      None
    '''

#     tb = self._getCaller()
#     logging.debug('Unlocking file %s (from: %s(%d): in %s <%d>).'
#                 % (fusepath, tb[0], tb[1], tb[2], thread.get_ident()))

    self._fileLocks[fusepath].release()

  def saveCachePolicy(self, filename):
    f = open(filename, 'w')
    for k,v in self._cacheSpec.iteritems():
      f.write("%s:%s\n" % (k,v))
    f.close()

  def loadCachePolicy(self, filename):
    f = open(filename, 'r')
    for line in f.readlines():
      k,v = line.strip().split(':')
      self._cacheSpec[k] = v
    f.close()

@extendedattribute('any', 'tsumufs.in-cache')
def xattr_inCache(type_, path, value=None):
  if value:
    return -errno.EOPNOTSUPP

  if tsumufs.cacheManager.isCachedToDisk(path):
    return '1'
  return '0'

@extendedattribute('any', 'tsumufs.dirty')
def xattr_isDirty(type_, path, value=None):
  if value:
    return -errno.EOPNOTSUPP

  if tsumufs.cacheManager.isCachedToDisk(path):
    return '1'
  return '0'

@extendedattribute('root', 'tsumufs.cached-dirents')
def xattr_cachedDirents(type_, path, value=None):
  if value:
    return -errno.EOPNOTSUPP

  return repr(tsumufs.cacheManager._cachedDirents)

@extendedattribute('root', 'tsumufs.cached-stats')
def xattr_cachedStats(type_, path, value=None):
  if value:
    return -errno.EOPNOTSUPP

  return repr(tsumufs.cacheManager._cachedStats)

@extendedattribute('any', 'tsumufs.should-cache')
def xattr_cachedStats(type_, path, value=None):

  if value:
    # set the value
    if value == '-':
      tsumufs.cacheManager._cacheSpec[path] = False
    elif value == '+':
      tsumufs.cacheManager._cacheSpec[path] = True
    elif value == '=':
      if tsumufs.cacheManager._cacheSpec.has_key(path):
        del tsumufs.cacheManager._cacheSpec[path]
    else:
      return -errno.EOPNOTSUPP
    return 0 # set is successfull

  if tsumufs.cacheManager._cacheSpec.has_key(path):
    if tsumufs.cacheManager._cacheSpec[path]:
      return '+'
    else:
      return '-'

  # not explicity named, so use our lookup code
  if tsumufs.cacheManager._shouldCacheFile(path):
    return '= (+)'
  return '= (-)'

