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

import sys

import tsumufs
from dataregion import *


class InodeChange(tsumufs.Debuggable):
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
  dataLength  = None

  def __repr__(self):
    '''
    Pretty printer method to give a bit more transparency into the
    object.
    '''

    rep = '<InodeChange %s' % repr(self.dataRegions)

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
    if self.dataLength:
      rep += ' dataLength: %d' % self.dataLength

    rep += '>'

    return rep

  def __str__(self):
    return repr(self)

  def __init__(self):
    self._setName('InodeChange')
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
        accumulator = r.mergeWith(accumulator)
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

  def truncateLength(self, newlength):
    '''
    Truncate any DataRegions and set our new dataLength.
    '''

    self._debug('Truncating to %d' % newlength)
    self.dataLength = newlength

    for index in range(len(self.dataRegions)-1, -1, -1):
      region = self.dataRegions[index]

      if region.getStart() >= newlength:
        self._debug('Removing %s -- start >= newlength' % region)
        del self.dataRegions[index]

      elif region.getEnd() > newlength:
        # Recreate the dataregion with the new data reduced in size to match the
        # new length
        self._debug('Truncating %s -- end >= newlength' % region)
        removal_length = region.getEnd() - newlength
        newregion = DataRegion(region.getStart(),
                               newlength,
                               region.getData()[0:-removal_length])
        self._debug('Truncated region is %s' % newregion)
        self.dataRegions[index] = newregion

  def setDataLength(self, newlength):
    '''
    Set the new data length.
    '''


    self.dataLength = newlength
