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
import sys
import time

from fuse import Fuse
from errno import *
from stat import *
from threading import Thread, Semaphore, Event

from pprint import pprint

from triumvirate import *
from nfsmount import *
from synclog import *

class SyncThread(Triumvirate, Thread):
  """Thread to handle cache management."""

  tsumuMountedEvent = None
  nfsMount = None
  syncQueue = None

  def __init__(self, tsumuMountedEvent, nfsMount):
    self.tsumuMountedEvent = tsumuMountedEvent
    self.nfsMount = nfsMount
    self.syncQueue = SyncQueue()
    self.syncQueue.load()
    self.syncQueue.validate()

    Thread.__init__(self, name="SyncThread")

  def run(self):
    while self.tsumuMountedEvent.isSet():
      while not self.nfsMount.connectedEvent.isSet():
        # Don't do anything until we have a valid NFS
        # connection.
        self.nfsMount.connectedEvent.wait()

      self.syncQueue.acquireLock()
      item = self.syncQueue.getItem()  # excludes conflicted changes
      self.syncQueue.releaseLock()

      try:
        # Verify that what the synclog contains is actually what is on
        # the filer.

        for change in item.preChangeContents():
          if self.nfsMount.getFileRegion(item.filename, change.start, change.end) != change.data:
            raise SyncConflictError(item)
          else:
            self.nfsMount.putFileRegion(item.filename,
                                        change.start,
                                        change.end,
                                        change.data)

      except IOError, e:
        # IO errors indicate something is wrong with the backend NFS
        # mount. Unset the connected event to trigger a remount if
        # possible.

        self.nfsConnectedEvent.unset()
      except SyncConflictError, e:
        # Do something here to attempt to merge data anyway for text
        # files, if possible. Failing that, mark the item as a
        # conflict in the synclog, and notify the user.

        if e.item.fileType != e.item.TEXT:
          item.markConflict()
          # notifyUser()

        try:
          # If we don't have any conflicts, we can proceed here -- the
          # original hasn't changed since we synced it to the cache
          # last. Just copy over the whole cache file on top of it.

          self.nfsMount.lockFile(item.filename)
          item.copyToNFS()
          self.nfsMount.unlockFile(item.filename)
          
          self.syncQueue.acquireLock()
          self.syncQueue.removeItem(item)
          self.syncQueue.flushToDisk()
          self.syncQueue.releaseLock()
        except IOError, e:
          self.nfsConnectedEvent.unset()
