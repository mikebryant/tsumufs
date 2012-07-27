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
import shutil
import sys
import time
import threading
import errno
import stat
import traceback

import logging
logger = logging.getLogger(__name__)

import fuse

import tsumufs
from extendedattributes import extendedattribute


CONFLICT_PREAMBLE = '''
# New changeset at %(timestamp)d
set = ChangeSet(%(timestamp)d)
'''

CONFLICT_POSTAMBLE = '''
try:
  changesets.append(set)
except NameError:
  changesets = [set]
changesets

'''

class SyncThread(threading.Thread):
  '''
  Thread to handle cache and NFS mount management.
  '''

  def __init__(self):
    logger.debug('Initializing.')

    # Install our custom exception handler so that any exceptions are
    # output to the syslog rather than to /dev/null.
    sys.excepthook = tsumufs.syslogExceptHook

    logger.debug('Loading SyncQueue.')
    tsumufs.syncLog = tsumufs.SyncLog()

    try:
      tsumufs.syncLog.loadFromDisk()
    except EOFError:
      logger.debug('Unable to load synclog. Aborting.')

    logger.debug('Setting up thread state.')
    threading.Thread.__init__(self, name='SyncThread')

    logger.debug('Initialization complete.')

  def _attemptMount(self):
    logger.debug('Attempting to mount NFS.')

    logger.debug('Checking for NFS server availability')
    if not tsumufs.nfsMount.pingServerOK():
      logger.debug('NFS ping failed.')
      return False

    logger.debug('NFS ping successful.')
    logger.debug('Checking NFS sanity.')
    if not tsumufs.nfsMount.nfsCheckOK():
      logger.debug('NFS sanity check failed.')
      return False

    logger.debug('NFS sanity check okay.')
    logger.debug('Attempting mount.')

    try:
      result = tsumufs.nfsMount.mount()
    except:
      logger.debug('Exception: %s' + traceback.format_exc())
      logger.debug('NFS mount failed.')
      tsumufs.nfsAvailable.clear()
      return False

    if result:
      logger.debug('NFS mount complete.')
      tsumufs.nfsAvailable.set()
      return True
    else:
      logger.debug('Unable to mount NFS.')
      tsumufs.nfsAvailable.clear()
      return False

  def _propogateNew(self, item, change):
    fusepath = item.getFilename()
    nfspath = tsumufs.nfsPathOf(fusepath)

    # Horrible hack, but it works to test for the existance of a file.
    try:
      tsumufs.nfsMount.readFileRegion(fusepath, 0, 0)
    except (OSError, IOError), e:
      if e.errno != errno.ENOENT:
        return True

    if item.getFileType() != 'dir':
      shutil.copy(tsumufs.cachePathOf(fusepath),
                  tsumufs.nfsPathOf(fusepath))
    else:
      perms = tsumufs.permsOverlay.getPerms(fusepath)
      os.mkdir(tsumufs.nfsPathOf(fusepath), perms.mode)
      os.chown(tsumufs.nfsPathOf(fusepath), perms.uid, perms.gid)

    return False

  def _propogateLink(self, item, change):
    # TODO(jtg): Add in hardlink support

    return False

  def _propogateUnlink(self, item, change):
    # TODO(conflicts): Conflict if the file type or inode have changed
    fusepath = item.getFilename()

    if item.getFileType() != 'dir':
      os.unlink(tsumufs.nfsPathOf(fusepath))
    else:
      os.rmdir(tsumufs.nfsPathOf(fusepath))

    return False

  def _propogateChange(self, item, change):
    # Rules:
    #   1. On conflict NFS always wins.
    #   2. Loser data always appended as a list of changes in
    #      ${mount}/._${file}.changes
    #   3. We're no better than NFS

    # Steps:
    #   1. Stat both files, and verify the file type is identical.
    #   2. Read in the regions from NFS.
    #   3. Compare the regions between the changes and NFS.
    #   4. If any changes differ, the entire set is conflicted.
    #      4a. Create a conflict change file and write out the changes
    #          that differ.
    #      4b. Create a 'new' change in the synclog for the conflict
    #          change file.
    #      4c. Erase the cached file on disk.
    #      4d. Invalidate dirent cache for the file's containing dir.
    #      4e. Invalidate the stat cache fo that file.
    #   5. Otherwise:
    #      4a. Iterate over each change and write it out to NFS.

    fusepath   = item.getFilename()
    logger.debug('Fuse path is %s' % fusepath)

    nfs_stat   = os.lstat(tsumufs.nfsPathOf(fusepath))
    cache_stat = os.lstat(tsumufs.cachePathOf(fusepath))

    logger.debug('Validating data hasn\'t changed on NFS.')
    if stat.S_IFMT(nfs_stat.st_mode) != stat.S_IFMT(cache_stat.st_mode):
      logger.debug('File type has completely changed -- conflicted.')
      return True
    elif nfs_stat.st_ino != item.getInum():
      logger.debug('Inode number changed -- conflicted.')
      return True
    else:
      # Iterate over each region, and verify the changes
      for region in change.getDataChanges():
        data = tsumufs.nfsMount.readFileRegion(fusepath,
                                               region.getStart(),
                                               region.getEnd()-region.getStart())

        if len(data) < region.getEnd() - region.getStart():
          data += '\x00' * ((region.getEnd() - region.getStart()) - len(data))

        if region.getData() != data:
          logger.debug('Region has changed -- entire changeset conflicted.')
          logger.debug('Data read was %s' % repr(data))
          logger.debug('Wanted %s' % repr(region.getData()))
          return True

    logger.debug('No conflicts detected.')

    # Propogate changes
    for region in change.getDataChanges():
      data = tsumufs.cacheManager.readFile(fusepath,
                                           region.getStart(),
                                           region.getEnd()-region.getStart(),
                                           os.O_RDONLY)

      # Pad the region with nulls if we get a short read (EOF before the end of
      # the real file. It means we ran into a truncate issue and that the file
      # is shorter than it was originally -- we'll propogate the truncate down
      # the line.
      if len(data) < region.getEnd() - region.getStart():
        data += '\x00' * ((region.getEnd() - region.getStart()) - len(data))

      logger.debug('Writing to %s at [%d-%d] %s'
                  % (fusepath, region.getStart(),
                     region.getEnd(), repr(data)))

      tsumufs.nfsMount.writeFileRegion(fusepath,
                                       region.getStart(),
                                       region.getEnd(),
                                       data)

    # Propogate truncations
    if (cache_stat.st_size < nfs_stat.st_size):
      tsumufs.nfsMount.truncateFile(fusepath, cache_stat.st_size)

    # TODO(writeback): Add in metadata syncing here.
    return False

  def _propogateRename(self, item, change):
    # TODO(conflicts): Verify inode numbers here
    oldfusepath = item.getOldFilename()
    newfusepath = item.getNewFilename()
    os.rename(tsumufs.nfsPathOf(item.getOldFilename()),
              tsumufs.nfsPathOf(item.getNewFilename()))

    return False

  def _writeChangeSet(self, item, change):
    # TODO(refactor): Make FileChange generate the patch set string instead.

    if item.getType() != 'rename':
      fusepath = item.getFilename()
    else:
      fusepath = item.getOldFilename()

    if fusepath[0] == '/':
      conflictpath = fusepath[1:]
    else:
      conflictpath = fusepath

    conflictpath = conflictpath.replace('/', '-')
    conflictpath = os.path.join(tsumufs.conflictDir, conflictpath)
    logger.debug('Using %s as the conflictpath.' % conflictpath)

    try:
      tsumufs.cacheManager.lockFile(fusepath)
      isNewFile = True
      fd = None

      try:
        logger.debug('Attempting open of %s' % conflictpath)
        tsumufs.cacheManager.fakeOpen(conflictpath,
                                      os.O_CREAT|os.O_APPEND|os.O_RDWR,
                                      0700 | stat.S_IFREG);
        fd = os.open(tsumufs.cachePathOf(conflictpath),
                     os.O_CREAT|os.O_APPEND|os.O_RDWR,
                     0700 | stat.S_IFREG)
        isNewFile = True
      except OSError, e:
        if e.errno != errno.EEXIST:
          raise

        isNewFile = False

        logger.debug('File existed -- reopening as O_APPEND' % conflictpath)
        tsumufs.cacheManager.fakeOpen(conflictpath,
                                      os.O_APPEND|os.O_RDWR|os.O_EXCL,
                                      0700 | stat.S_IFREG);
        fd = os.open(tsumufs.cachePathOf(conflictpath),
                     os.O_APPEND|os.O_RDWR|os.O_EXCL,
                     0700 | stat.S_IFREG)

      fp = os.fdopen(fd, 'r+')
      startPos = fp.tell()
      fp.close()

      # Write the changeset preamble
      logger.debug('Writing preamble.')
      tsumufs.cacheManager.writeFile(conflictpath, -1,
                                     CONFLICT_PREAMBLE %
                                     { 'timestamp': time.time() },
                                     os.O_APPEND|os.O_RDWR)

      if item.getType() == 'new':
        # TODO(conflicts): Write the entire file to the changeset as one large
        # patch.
        logger.debug('New file -- don\'t know what to do -- skipping.')
        pass

      if item.getType() == 'change':
        # TODO(conflicts): Propogate metadata changes as well.
        # TODO(conflicts): Propogate truncates!

        # Write changes to file
        logger.debug('Writing changes to conflict file.')
        for region in change.getDataChanges():
          data = tsumufs.cacheManager.readFile(fusepath,
                                               region.getStart(),
                                               region.getEnd()-region.getStart(),
                                               os.O_RDONLY)
          tsumufs.cacheManager.writeFile(conflictpath, -1,
                                         'set.addChange(type_="patch", start=%d, end=%d, data=%s)' %
                                         (region.getStart(), region.getEnd(), repr(data)),
                                         os.O_APPEND|os.O_RDWR)

      if item.getType() == 'link':
        # TODO(conflicts): Implement links.
        logger.debug('Link file -- don\'t know what to do -- skipping.')
        pass

      if item.getType() == 'unlink':
        fp.write('set.addUnlink()')

      if item.getType() == 'symlink':
        # TODO(conflicts): Implement symlinks.
        logger.debug('Symlink file -- don\'t know what to do -- skipping.')
        pass

      if item.getType() == 'rename':
        logger.debug('Rename file -- don\'t know what to do -- skipping.')
        pass

      logger.debug('Writing postamble.')
      tsumufs.cacheManager.writeFile(conflictpath, -1, CONFLICT_POSTAMBLE,
                                     os.O_APPEND|os.O_RDWR)

      logger.debug('Getting file size.')
      fp = open(tsumufs.cachePathOf(conflictpath), 'r+')
      fp.seek(0, 2)
      endPos = fp.tell()
      fp.close()

      if isNewFile:
        logger.debug('Conflictfile was new -- adding to synclog.')
        tsumufs.syncLog.addNew('file', filename=conflictpath)

        perms = tsumufs.cacheManager.statFile(fusepath)
        tsumufs.permsOverlay.setPerms(conflictpath, perms.st_uid, perms.st_gid,
                                      0700 | stat.S_IFREG)
        logger.debug('Setting permissions to (%d, %d, %o)' % (perms.st_uid,
                                                             perms.st_gid,
                                                             0700 | stat.S_IFREG))
      else:
        logger.debug('Conflictfile was preexisting -- adding change.')
        tsumufs.syncLog.addChange(conflictpath, -1,
                                  startPos, endPos,
                                  '\x00' * (endPos - startPos))
    finally:
      tsumufs.cacheManager.unlockFile(fusepath)

  def _validateConflictDir(self, conflicted_path):
    try:
      try:
        tsumufs.cacheManager.lockFile(tsumufs.conflictDir)

        try:
          tsumufs.cacheManager.statFile(tsumufs.conflictDir)

        except (IOError, OSError), e:
          if e.errno != errno.ENOENT:
            raise

          perms = tsumufs.cacheManager.statFile(conflicted_path)

          logger.debug('Conflict dir missing -- creating.')
          tsumufs.cacheManager.makeDir(tsumufs.conflictDir)

          logger.debug('Setting permissions.')
          tsumufs.permsOverlay.setPerms(tsumufs.conflictDir,
                                        perms.st_uid,
                                        perms.st_gid,
                                        0700 | stat.S_IFDIR)

          logger.debug('Adding to synclog.')
          tsumufs.syncLog.addNew('dir', filename=tsumufs.conflictDir)

        else:
          logger.debug('Conflict dir already existed -- not recreating.')

      except Exception, e:
        exc_info = sys.exc_info()

        logger.debug('*** Unhandled exception occurred')
        logger.debug('***     Type: %s' % str(exc_info[0]))
        logger.debug('***    Value: %s' % str(exc_info[1]))
        logger.debug('*** Traceback:')

        for line in traceback.extract_tb(exc_info[2]):
          logger.debug('***    %s(%d) in %s: %s' % line)

    finally:
      tsumufs.cacheManager.unlockFile(tsumufs.conflictDir)

  def _handleConflicts(self, item, change):
    if item.getType() != 'rename':
      fusepath = item.getFilename()
    else:
      fusepath = item.getOldFilename()

    logger.debug('Validating %s exists.' % tsumufs.conflictDir)
    self._validateConflictDir(fusepath)

    logger.debug('Writing changeset to conflict file.')
    self._writeChangeSet(item, change)

    logger.debug('De-caching file %s.' % fusepath)
    tsumufs.cacheManager.removeCachedFile(fusepath)

  def _handleChange(self, item, change):
    try:
      type_ = item.getType()
      change_types = { 'new': self._propogateNew,
                       'link': self._propogateLink,
                       'unlink': self._propogateUnlink,
                       'change': self._propogateChange,
                       'rename': self._propogateRename }

      logger.debug('Calling propogation method %s' % change_types[type_].__name__)

      found_conflicts = change_types[type_].__call__(item, change)

      if found_conflicts:
        logger.debug('Found conflicts. Running handler.')
        self._handleConflicts(item, change)
      else:
        logger.debug('No conflicts detected. Merged successfully.')

    except Exception, e:
      exc_info = sys.exc_info()

      logger.debug('*** Unhandled exception occurred')
      logger.debug('***     Type: %s' % str(exc_info[0]))
      logger.debug('***    Value: %s' % str(exc_info[1]))
      logger.debug('*** Traceback:')

      for line in traceback.extract_tb(exc_info[2]):
        logger.debug('***    %s(%d) in %s: %s' % line)

  def run(self):
    try:
      while not tsumufs.unmounted.isSet():
        logger.debug('TsumuFS not unmounted yet.')

        while (not tsumufs.nfsAvailable.isSet()
               and not tsumufs.unmounted.isSet()):
          logger.debug('NFS unavailable')

          if not tsumufs.forceDisconnect.isSet():
            self._attemptMount()
            tsumufs.unmounted.wait(5)
          else:
            logger.debug(('...because user forced disconnect. '
                         'Not attempting mount.'))
            time.sleep(5)

        while tsumufs.syncPause.isSet():
          logger.debug('User requested sync pause. Sleeping.')
          time.sleep(5)

        while (tsumufs.nfsAvailable.isSet()
               and not tsumufs.unmounted.isSet()
               and not tsumufs.syncPause.isSet()):
          try:
            logger.debug('Checking for items to sync.')
            (item, change) = tsumufs.syncLog.popChange()

          except IndexError:
            logger.debug('Nothing to sync. Sleeping.')
            time.sleep(5)
            continue

          logger.debug('Got one: %s' % repr(item))

          try:
            # Handle the change
            logger.debug('Handling change.')
            self._handleChange(item, change)

            # Mark the change as complete.
            logger.debug('Marking change %s as complete.' % repr(item))

            try:
              tsumufs.syncLog.finishedWithChange(item)
            except Exception, e:
              exc_info = sys.exc_info()

              logger.debug('*** Unhandled exception occurred')
              logger.debug('***     Type: %s' % str(exc_info[0]))
              logger.debug('***    Value: %s' % str(exc_info[1]))
              logger.debug('*** Traceback:')

              for line in traceback.extract_tb(exc_info[2]):
                logger.debug('***    %s(%d) in %s: %s' % line)

          except IOError, e:
            logger.debug('Caught an IOError in the middle of handling a change: '
                        '%s' % str(e))

            logger.debug('Disconnecting from NFS.')
            tsumufs.nfsAvailable.clear()
            tsumufs.nfsMount.unmount()

            logger.debug('Not removing change from the synclog, but finishing.')
            tsumufs.syncLog.finishedWithChange(item, remove_item=False)

      logger.debug('Shutdown requested.')
      logger.debug('Unmounting NFS.')

      try:
        tsumufs.nfsMount.unmount()
      except:
        logger.debug('Unable to unmount NFS -- caught an exception.')
        tsumufs.syslogCurrentException()
      else:
        logger.debug('NFS unmount complete.')

      logger.debug('Saving synclog to disk.')

      try:
        tsumufs.syncLog.flushToDisk()
      except Exception, e:
        logger.debug('Unable to save synclog -- caught an exception.')
        tsumufs.syslogCurrentException()
      else:
        logger.debug('Synclog saved.')

      logger.debug('SyncThread shutdown complete.')

    except Exception, e:
      tsumufs.syslogCurrentException()


@extendedattribute('root', 'tsumufs.pause-sync')
def xattr_pauseSync(type_, path, value=None):
  try:
    if value != None:
      if value == '0':
        tsumufs.syncPause.clear()
      elif value == '1':
        tsumufs.syncPause.set()
      else:
        return -errno.EOPNOTSUPP
      return

    if tsumufs.syncPause.isSet():
      return '1'

    return '0'
  except:
    return -errno.EOPNOTSUPP

@extendedattribute('root', 'tsumufs.force-disconnect')
def xattr_forceDisconnect(type_, path, value=None):
  try:
    if value != None:
      if value == '0':
        tsumufs.forceDisconnect.clear()
      elif value == '1':
        tsumufs.forceDisconnect.set()
        tsumufs.nfsMount.unmount()
        tsumufs.nfsAvailable.clear()
      else:
        return -errno.EOPNOTSUPP
      return

    if tsumufs.forceDisconnect.isSet():
      return '1'

    return '0'
  except:
    return -errno.EOPNOTSUPP

@extendedattribute('root', 'tsumufs.connected')
def xattr_connected(type_, path, value=None):
  if value != None:
    return -errno.EOPNOTSUPP

  if tsumufs.nfsAvailable.isSet():
    return '1'

  return '0'
