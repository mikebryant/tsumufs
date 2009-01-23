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
import shutil
import sys
import time
import threading
import errno
import stat
import traceback

import fuse

import tsumufs
from extendedattributes import extendedattribute


class SyncThread(tsumufs.Triumvirate, threading.Thread):
  '''
  Thread to handle cache and NFS mount management.
  '''

  def __init__(self):
    self._debug('Initializing.')

    # Install our custom exception handler so that any exceptions are
    # output to the syslog rather than to /dev/null.
    sys.excepthook = tsumufs.syslogExceptHook

    self._debug('Loading SyncQueue.')
    tsumufs.syncLog = tsumufs.SyncLog()

    try:
      tsumufs.syncLog.loadFromDisk()
    except EOFError:
      self._debug('Unable to load synclog. Aborting.')

    self._debug('Setting up thread state.')
    threading.Thread.__init__(self, name='SyncThread')

    self._debug('Initialization complete.')

  def _attemptMount(self):
    self._debug('Attempting to mount NFS.')

    self._debug('Checking for NFS server availability')
    if not tsumufs.nfsMount.pingServerOK():
      self._debug('NFS ping failed.')
      return False

    self._debug('NFS ping successful.')
    self._debug('Checking NFS sanity.')
    if not tsumufs.nfsMount.nfsCheckOK():
      self._debug('NFS sanity check failed.')
      return False

    self._debug('NFS sanity check okay.')
    self._debug('Attempting mount.')

    try:
      result = tsumufs.nfsMount.mount()
    except:
      self._debug('Exception: %s' + traceback.format_exc())
      self._debug('NFS mount failed.')
      tsumufs.nfsAvailable.clear()
      return False

    if result:
      self._debug('NFS mount complete.')
      tsumufs.nfsAvailable.set()
      return True
    else:
      self._debug('Unable to mount NFS.')
      tsumufs.nfsAvailable.clear()
      return False

  def _propogateNew(self, item, change):
    # TODO(conflicts): Conflict if the file already exists.
    fusepath = item.getFilename()
    shutil.copy(tsumufs.cachePathOf(fusepath),
                tsumufs.nfsPathOf(fusepath))

  def _propogateLink(self, item, change):
    # TODO(jtg): Add in hardlink support
    pass

  def _propogateUnlink(self, item, change):
    # TODO(conflicts): Conflict if the file type or inode have changed
    fusepath = item.getFilename()
    os.unlink(tsumufs.nfsPathOf(fusepath))

  def _propogateChange(self, item, change):
    # Rules:
    # 1. On conflict NFS always wins.
    # 2. Loser data always appended as a list of changes in
    #    ${mount}/._${file}.changes
    # 3. We're no better than NFS

    # Steps:
    # 1. Stat both files, and verify the file type is identical.
    # 2. Read in the regions from NFS.
    # 3. Compare the regions between the changes and NFS.
    # 4. If any changes differ, the entire set is conflicted.
    #    4a. Create a conflict change file and write out the changes
    #        that differ.
    #    4b. Create a 'new' change in the synclog for the conflict
    #        change file.
    #    4c. Erase the cached file on disk.
    #    4d. Invalidate dirent cache for the file's containing dir.
    #    4e. Invalidate the stat cache fo that file.
    # 5. Otherwise:
    #    4a. Iterate over each change and write it out to NFS.

    is_conflicted = False
    fusepath   = item.getFilename()
    nfs_stat   = os.lstat(tsumufs.nfsPathOf(fusepath))
    cache_stat = os.lstat(tsumufs.cachePathOf(fusepath))

    if stat.ISFMT(nfs_stat.st_mode) != stat.ISFMT(cache_stat.st_mode):
      is_conflicted = True
    elif nfs_stat.st_size != item.dataLength:
      is_conflicted = True
    else:
      # Iterate over each region, and verify the changes
      for region in change.getDataChanges():
        data = tsumufs.nfsMount.readFile(fusepath,
                                         region.getStart(),
                                         region.getEnd()-region.getStart(),
                                         os.O_RDONLY)
        if region.getData() != data:
          is_conflicted = True
          break

    if is_conflicted:
      return True

    # Propogate truncations
    if (change.dataLength < nfs_stat.st_size):
      tsumufs.nfsMount.truncateFile(fusepath, change.dataLength)

    # Propogate changes
    for region in change.getDataChanges():
      data = tsumufs.cacheManager.readFile(fusepath,
                                           region.getStart(),
                                           region.getEnd()-region.getStart(),
                                           os.O_RDONLY)

      self._debug('Writing to %s at [%d-%d] %s'
                  % (fusepath, region.getStart(),
                     region.getEnd(), repr(data)))

      tsumufs.nfsMount.writeFileRegion(fusepath,
                                       region.getStart(),
                                       region.getEnd(),
                                       data)

    # TODO(writeback): Add in metadata syncing here.

    return False

  def _propogateRename(self, item, change):
    # TODO(conflicts): Verify inode numbers here
    oldfusepath = item.getOldFilename()
    newfusepath = item.getNewFilename()
    os.rename(tsumufs.nfsPathOf(item.getOldFilename()),
              tsumufs.nfsPathOf(item.getNewFilename()))

  def _handleChange(self, item, change):
    type_ = item.getType()
    change_types = { 'new': self._propogateNew,
                     'link': self._propogateLink,
                     'unlink': self._propogateUnlink,
                     'change': self._propogateChange,
                     'rename': self._propogateRename }

    found_conflicts = change_types[type_].__call__(self, item, change)

    if found_conflicts:
      self._handleConflicts(item, change)

  def run(self):
    try:
      while not tsumufs.unmounted.isSet():
        self._debug('TsumuFS not unmounted yet.')

        while (not tsumufs.nfsAvailable.isSet()
               and not tsumufs.unmounted.isSet()):
          self._debug('NFS unavailable')

          if not tsumufs.forceDisconnect.isSet():
            self._attemptMount()
            tsumufs.unmounted.wait(5)
          else:
            self._debug(('...because user forced disconnect. '
                         'Not attempting mount.'))
            time.sleep(5)

        while tsumufs.syncPause.isSet():
          self._debug('User requested sync pause. Sleeping.')
          time.sleep(5)

        while (tsumufs.nfsAvailable.isSet()
               and not tsumufs.unmounted.isSet()
               and not tsumufs.syncPause.isSet()):
          try:
            self._debug('Checking for items to sync.')
            (item, change) = tsumufs.syncLog.popChange()

          except IndexError:
            self._debug('Nothing to sync. Sleeping.')
            time.sleep(5)
            continue

          self._debug('Got one: %s' % repr(item))

          try:
            # Handle the change
            self._handleChange(item, change)

            # Mark the change as complete.
            self._debug('Marking change %s as complete.' % repr(item))
            tsumufs.syncLog.finishedWithChange(item)

          except IOError, e:
            self._debug('Caught an IOError in the middle of handling a change: '
                        '%s' % str(e))

            self._debug('Disconnecting from NFS.')
            tsumufs.nfsAvailable.clear()
            tsumufs.nfsMount.unmount()

            self._debug('Not removing change from the synclog, but finishing.')
            tsumufs.syncLog.finishedWithChange(item, remove_item=False)

      self._debug('Shutdown requested.')
      self._debug('Unmounting NFS.')

      try:
        tsumufs.nfsMount.unmount()
      except:
        self._debug('Unable to unmount NFS -- caught an exception.')
        tsumufs.syslogCurrentException()
      else:
        self._debug('NFS unmount complete.')

      self._debug('Saving synclog to disk.')

      try:
        tsumufs.syncLog.flushToDisk()
      except Exception, e:
        self._debug('Unable to save synclog -- caught an exception.')
        tsumufs.syslogCurrentException()
      else:
        self._debug('Synclog saved.')

      self._debug('SyncThread shutdown complete.')

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
