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

from dataregion import *
from threading import Lock

class InodeChange:
  """Class that represents any change to an inode and the data that it
  points to."""

  dataRegions = []
  ctime       = None
  mtime       = None
  permissions = None
  uid         = None
  gid         = None
  symlinkPath = None
  dataLength  = None

  def __repr__(self):
    """Pretty printer method to give a bit more transparency into the
    object."""

    repr = "<InodeChange ["
    if len(self.dataRegions) > 0:
      for r in self.dataRegions:
        repr += "%s" % r
        if r != self.dataRegions[-1]:
          repr += "\n" + (" " * 14)
          repr += "]"
          
      if self.ctime:
        repr += "\n\tctime: %d" % self.ctime
      if self.mtime:
        repr += "\n\tmtime: %d" % self.mtime
      if self.permissions:
        repr += "\n\tperms: %d" % self.permissions
      if self.uid:
        repr += "\n\tuid: %d" % self.uid
      if self.gid:
        repr += "\n\tgid: %d" % self.gid
      if self.symlinkPath:
        repr += "\n\tsymlinkPath: %s" % self.symlinkPath
      repr += ">"

    return repr

  def __init__(self):
    pass

  def addDataChange(self, start, end, data):
    """Method to add a representation of a change in data in an inode. Can
    throw an InvalidRegionSpecified and
    RegionDoesNotMatchLengthError. Note that this method attempts to
    auto-merge the change with other lists already existing if it
    can."""
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
    """Method to return a list of changes made to the data
    pointed to by this inode."""
    return self.dataRegions

class InodeMap(object):
  """Singleton object whose implementation is borrowed directly from the
  ASPN: Python Cookbook at
  <http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/52558>."""

  class __impl(object):
    """Implementation of the Singleton object as described in the
    docstring for InodeMap.

    This class implements a pair of mappings of inode numbers to
    filenames and back to the reverse. The mappings are implemented as
    a singleton so that all objects in all threads may access this
    data. This class also implements __getstate__() and __setstate__()
    so that upon pickling, only the hashes are stored, excluding the
    internal locks used to serialize write access."""

    __inumToFileHash = {}
    __fileToInumHash = {}
    __lock = Lock()

    def __init__(self):
      pass

    def __getstate__(self):
      self.__lock.acquire()
      retval = [self.__inumToFileHash, self.__fileToInumHash]
      self.__lock.release()
      return retval

    def __setstate__(self, args):
      self.__inumToFileHash = args[0]
      self.__fileToInumHash = args[1]
      self.__lock = Lock()

      def addMapping(self, inum, filename):
        self.__lock.acquire()
        if self.__inumToFileHash.has_key(inum):
          self.__inumToFileHash[inum].append(filename)
        else:
          self.__inumToFileHash[inum] = [filename]
          self.__fileToInumHash[filename] = inum
        self.__lock.release()

      def lookupByInum(self, inum):
        self.__lock.acquire()
        retval = {inum: self.__inumToFileHash[inum]}
        self.__lock.release()
        return retval

      def lookupByFilename(self, filename):
        self.__lock.acquire()
        inum = self.__fileToInumHash[filename]
        retval = {inum: self.__inumToFileHash[inum]}
        self.__lock.release()
        return retval

  __instance = None

  def __init__(self):
    if InodeMap.__instance == None:
      InodeMap.__instance = InodeMap.__impl()
      self.__dict__['_InodeMap__instance'] = InodeMap.__instance

  def __getattr__(self, attr):
    return getattr(self.__instance, attr)

  def __setattr__(self, attr, value):
    setattr(self.__instance, attr, value)


