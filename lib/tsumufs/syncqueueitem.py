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

import cPickle

from inode import *
from dataregion import *

class SyncQueueItem:
  _type = None        # 'new|'link|'unlink|'change|'rename
  _file_type = None   # 'file|'dir|'socket|'fifo|'device
  _dev_type = None    # 'char|'block
  _filename = None    # string
  _old_fname = None   # string
  _new_fname = None   # string
  _inum = None        # inode number

  _hargs = None

  def __init__(self, type, **hargs):
    self._type = type
    self._hargs = hargs

  def getChanges(self):
    """Calculate the differences in the synclog and the file located in
    the cache. For each change, generate a SyncChange that it
    represents, and return a list containing all of these changes."""
    pass
