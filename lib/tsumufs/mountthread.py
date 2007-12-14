#!/usr/bin/python2.4
#
# Copyright (C) 2007  Google, Inc. All Rights Reserved.
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

class MountThread(Triumvirate, Thread):
  """Thread to verify that the NFS mount is actually mounted when the
  backend server is available and healthy and stays that way until one
  of the other threads flag it as being down again."""

  tsumuMountedEvent = None
  nfsMount = None

  def __init__(self, tsumuMountedEvent, nfsMount):
    self.tsumuMountedEvent = tsumuMountedEvent
    self.nfsMount = nfsMount
    Thread.__init__(self, name="MountThread")

  def run(self):
    while self.tsumuMountedEvent.isSet():
      while not self.nfsMount.connectedEvent.isSet():
        if self.nfsMount.pingServerOK():
          if self.nfsMount.nfsCheckOK():
            self.nfsMount.mount()
            time.sleep(5)

      while self.nfsMount.connectedEvent.isSet():
        time.sleep(5)
      
    self.nfsMount.unmount()
