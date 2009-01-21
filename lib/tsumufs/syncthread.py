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
            # excludes conflicted changes
            self._debug('Checking for items to sync.')

            (item, change) = tsumufs.syncLog.popChange()

          except IndexError:
            self._debug('Nothing to sync. Sleeping.')
            time.sleep(5)
            continue
          else:
            self._debug('Got one: %s' % repr(item))

          try:
            # Verify that what the synclog contains is actually what is on
            # the file server.

            if item.getType() == 'change':
              for region in change.getDataChanges():
                olddata = region.getData()
                nfsdata = tsumufs.nfsMount.readFileRegion(item.getFilename(),
                                                          region.getStart(),
                                                          region.getEnd())

                if nfsdata != olddata:
                  raise tsumufs.SyncConflictError(item)

          except IOError, e:
            # IO errors indicate something is wrong with the backend NFS
            # mount. Unset the connected event to trigger a remount if
            # possible.

            self._debug('Caught an IOError: %s' % str(e))
            self._debug('Disconnecting from NFS.')

            tsumufs.nfsAvailable.clear()
            tsumufs.nfsMount.unmount()
            continue

          except tsumufs.SyncConflictError, e:
            # Do something here to attempt to merge data anyway for text
            # files, if possible. Failing that, mark the item as a
            # conflict in the synclog, and notify the user.

            # TODO(jtg): Handle conflicts!
            pass

          try:
            # If we don't have any conflicts, we can proceed here -- the
            # original hasn't changed since we synced it to the cache
            # last.

            # TODO(locks): Maybe make the popItem() call lock the paths
            # first, and then call out to a secondary finishedWithItem() method
            # on the SyncLog? This would alleviate race conditions with the
            # below code.

            if item.getType() == 'new':
              fusepath = item.getFilename()

              shutil.copy(tsumufs.cachePathOf(fusepath),
                          tsumufs.nfsPathOf(fusepath))

            elif item.getType() == 'link':
              # TODO(jtg): Add in hardlink support
              pass

            elif item.getType() == 'unlink':
              fusepath = item.getFilename()

              os.unlink(tsumufs.nfsPathOf(fusepath))

            elif item.getType() == 'change':
              fusepath = item.getFilename()

              statgoo  = tsumufs.cacheManager.statFile(fusepath)

              # Propogate truncations
              if (change.dataLength < statgoo.st_size):
                tsumufs.nfsMount.truncateFile(fusepath, change.dataLength)

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

             # TODO(jtg): Add in metadata syncing here.

            elif item.getType() == "rename":
              oldfusepath = item.getOldFilename()
              newfusepath = item.getNewFilename()

              os.rename(tsumufs.nfsPathOf(item.getOldFilename()),
                        tsumufs.nfsPathOf(item.getNewFilename()))

            # Mark the change as complete.
            self._debug('Marking change %s as complete.' % repr(item))
            tsumufs.syncLog.finishedWithChange(item)

          except IOError, e:
            self._debug('Caught an IOError: %s' % str(e))
            self._debug('Disconnecting from NFS.')

            tsumufs.nfsAvailable.clear()
            tsumufs.nfsMount.unmount()

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
