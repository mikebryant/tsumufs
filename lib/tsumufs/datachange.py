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

import sys

import logging
logger = logging.getLogger(__name__)

import tsumufs
from dataregion import *


class DataChange(object):
  '''
  Class that represents any change to an inode and the data that it
  points to.
  '''

  dataRegions = []
  ctime       = None
  mtime       = None
  permissions = None
  uid         = None
  gid         = None
  symlinkPath = None

  def __repr__(self):
    '''
    Pretty printer method to give a bit more transparency into the
    object.
    '''

    rep = '<DataChange %s' % repr(self.dataRegions)

    if self.ctime:
      rep += ' ctime: %d' % self.ctime
    if self.mtime:
      rep += ' mtime: %d' % self.mtime
    if self.permissions:
      rep += ' perms: %o' % self.permissions
    if self.uid:
      rep += ' uid: %d' % self.uid
    if self.gid:
      rep += ' gid: %d' % self.gid
    if self.symlinkPath:
      rep += ' symlinkPath: %s' % self.symlinkPath

    rep += '>'

    return rep

  def __str__(self):
    return repr(self)

  def __init__(self):
    self._setName('DataChange')
    sys.excepthook = tsumufs.syslogExceptHook

  def addDataChange(self, start, end, data):
    '''
    Method to add a representation of a change in data in an inode. Can
    throw an InvalidRegionSpecified and
    RegionDoesNotMatchLengthError. Note that this method attempts to
    auto-merge the change with other lists already existing if it
    can.
    '''

    accumulator = DataRegion(start, end, data)
    newlist = []

    for r in self.dataRegions:
      if r.canMerge(accumulator):
        accumulator = accumulator.mergeWith(r)
      else:
        newlist.append(accumulator)
        accumulator = r

    newlist.append(accumulator)
    self.dataRegions = newlist

  def getDataChanges(self):
    '''
    Method to return a list of changes made to the data
    pointed to by this inode.
    '''

    return self.dataRegions
