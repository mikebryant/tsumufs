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

import tsumufs

from triumvirate import *
from nfsmount import *
from synclog import *

class MountThread(Triumvirate, Thread):
  """Thread to verify that the NFS mount is actually mounted when the
  backend server is available and healthy and stays that way until one
  of the other threads flag it as being down again."""

  def __init__(self):
    Thread.__init__(self, name="MountThread")

  def run(self):
    self.debug("Entered run loop")
    
    while tsumufs.mountedEvent.isSet():
      while not tsumufs.nfsConnectedEvent.isSet():
        time.sleep(5)
        self.debug("Checking for NFS server availability")
        if tsumufs.nfsMount.pingServerOK():
          self.debug("NFS ping looks good")
          if tsumufs.nfsMount.nfsCheckOK():
            self.debug("NFS sanity check okay. Attempting mount.")
            tsumufs.nfsMount.mount()

      self.debug("NFS mount complete.")
            
      while tsumufs.nfsConnectedEvent.isSet():
        self.debug("NFS connection alive.")
        time.sleep(5)

      self.debug("NFS connection lost")

    self.debug("Unmount requested -- unmounting NFS")
    tsumufs.nfsMount.unmount()
