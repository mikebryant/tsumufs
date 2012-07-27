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

import os
import os.path
import sys

import logging
logger = logging.getLogger(__name__)

import tsumufs


class NameToInodeMap(object):
  '''
  Class to help map pathnames to inode numbers and vise-versa.
  '''

  # TODO(ajs): This whole thing breaks when linkcount > 1

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

  # TODO(jtg): Need a way to unassociate an inode number from a name and
  # vice-versa.

  @classmethod
  def invalidate(cls):
    cls._namei = {}
    cls._iname = {}
