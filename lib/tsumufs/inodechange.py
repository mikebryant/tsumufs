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

from dataregion import *


class InodeChange:
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

    rep = '<InodeChange ['
    if len(self.dataRegions) > 0:
      for r in self.dataRegions:
        rep += '%s' % r
        if r != self.dataRegions[-1]:
          rep += '\n' + (' ' * 14)
          rep += ']'

      if self.ctime:
        rep += '\n\tctime: %d' % self.ctime
      if self.mtime:
        rep += '\n\tmtime: %d' % self.mtime
      if self.permissions:
        rep += '\n\tperms: %d' % self.permissions
      if self.uid:
        rep += '\n\tuid: %d' % self.uid
      if self.gid:
        rep += '\n\tgid: %d' % self.gid
      if self.symlinkPath:
        rep += '\n\tsymlinkPath: %s' % self.symlinkPath
      rep += '>'

    return rep

  def __str__(self):
    return repr(self)

  def __init__(self):
    pass

  def addDataChange(self, start, end, data):
    '''
    Method to add a representation of a change in data in an inode. Can
    throw an InvalidRegionSpecified and
    RegionDoesNotMatchLengthError. Note that this method attempts to
    auto-merge the change with other lists already existing if it
    can.
    '''

    merged = DataRegion(start, end, data)
    newlist = []

    for r in self.dataRegions:
      if r.canMerge(merged):
        merged = r.mergeWith(merged)
      else:
        newlist.append(r)

      newlist.insert(0, merged)
      self.dataRegions = newlist

  def getDataChanges(self):
    '''
    Method to return a list of changes made to the data
    pointed to by this inode.
    '''

    return self.dataRegions
