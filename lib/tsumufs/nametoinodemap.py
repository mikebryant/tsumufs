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
import os.path
import sys

import tsumufs

class NameToInodeMap(tsumufs.Debuggable):
  '''
  Class to help map pathnames to inode numbers and vise-versa.
  '''

  _namei = {}  # A hash of pathname -> inode number
  _iname = {}  # A hash of inode numbers -> a list of pathnames

  def __init__(self):
    pass

  @classmethod
  def nameToInode(cls, pathname):
    return cls._namei[pathname]

  @classmethod
  def inodeToName(cls, inode):
    return cls._iname[inode]

  @classmethod
  def _updateMap(cls, pathname, inode):
    cls._namei[pathname] = inode

    if cls._iname.has_key(inode):
      if not pathname in cls._iname[inode]:
        cls._iname[inode] += [ pathname ]
    else:
      cls._iname[inode] = [ pathname ]

  @classmethod
  def setNameToInode(cls, pathname, inode):
    cls._updateMap(pathname, inode)

  @classmethod
  def setInodeToName(cls, inode, pathname):
    cls._updateMap(pathname, inode)

  @classmethod
  def invalidate(cls):
    cls._namei = {}
    cls._iname = {}
