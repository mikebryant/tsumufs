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
import sys
import time
import threading
import errno
import stat
import traceback
import Queue

import fuse

import tsumufs


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
    except (EOFError), e:
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

            # TODO(jtg): Fix this.
            #item = tsumufs.syncLog.getChange()
            raise Queue.Empty()
          except Queue.Empty:
            self._debug('Nothing to sync. Sleeping.')
            time.sleep(5)
            continue
          else:
            self._debug('Got one.')

          try:
            # Verify that what the synclog contains is actually what is on
            # the file server.

            for change in item.preChangeContents():
              if tsumufs.nfsMount.getFileRegion(item.filename,
                                                change.start,
                                                change.end) != change.data:
                raise tsumufs.SyncConflictError(item)
              else:
                tsumufs.nfsMount.putFileRegion(item.filename,
                                               change.start,
                                               change.end,
                                               change.data)

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

            if e.item.fileType != e.item.TEXT:
              item.markConflict()
              # notifyUser()
              continue

          try:
            # If we don't have any conflicts, we can proceed here -- the
            # original hasn't changed since we synced it to the cache
            # last. Just copy over the whole cache file on top of it.

            tsumufs.nfsMount.lockFile(item.filename)
            item.copyToNFS()
            tsumufs.nfsMount.unlockFile(item.filename)

            tsumufs.syncQueue.remove(item)
            tsumufs.syncQueue.flushToDisk()

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
