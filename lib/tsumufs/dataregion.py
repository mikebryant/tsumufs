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

class RangeError(Exception):
  """Exception for representing a range error."""
  pass

class RegionError(Exception):
  """Exception to signal when a general region error has occured."""
  pass

class RegionLengthError(RegionError):
  """Exception to signal when a region length does not match it's
  range."""
  pass

class RegionOverlapError(RegionError):
  """Exception to signal when a region overlap error has
  occurred. Typically when a DataRegion::mergeWith call has been made
  with the argument being a region that cannot be merged."""
  pass

class DataRegion(object):
  _data   = None
  _start  = 0
  _end    = 0
  _length = 0

  def getData(self):
    return self._data

  def getStart(self):
    return self._start

  def getEnd(self):
    return self._end

  def __len__(self):
    return self._length

  def __repr__(self):
    """Method to display a somewhat transparent representation of a
    DataRegion object."""
    return("<DataRegion [%d:%d] (%d): \"%s\">"
           % (self.start, self.end, self.length, self.data))

  def __init__(self, start, end, data):
    """Initializer. Can raise InvalidRegionSpecifiedError and
    RegionDoesNotMatchLengthError."""
    if (end < start):
      raise RangeError, ("End of range is before start (%d, %d)"
                         % (start, end))

    if ((end - start + 1) != len(data)):
      raise RegionLengthError, ("Range specified does not match"+
                                "the length of the data given.")

    self.start = start
    self.end = end
    self.data = data
    self.length = len(data)

  def canMerge(self, dataregion):
    if ((dataregion.start > self.end) or       #       |-----|
        (dataregion.end < self.start)):        # |====|
      if ((self.end + 1 == dataregion.start) or
          (dataregion.end + 1 == self.start)):
        return True
      else:
        return False
    elif ((dataregion.start >= self.start) and #    |-----|
          (dataregion.start <= self.end)):     #       |=====|
      return True
    elif ((dataregion.end >= self.start) and   #    |-----|
          (dataregion.end <= self.end)):       # |=====|
      return True
    elif ((dataregion.start < self.start) and  #    |-----|
          (dataregion.end > self.end)):        # |===========|
      return True

  def mergeWith(self, dataregion):
    """Attempt to merge the given DataRegion into the current
    instance. Raises RegionError if the given DataRegion does not
    overlap with the self."""

    if (not self.canMerge(dataregion)):
      # Catch the invalid case where the region doesn't overlap
      # or is not adjacent.
      raise RegionOverlapError, ("The DataRegion given does "+
                                 "not overlap this instance "+
                                 "(%s, %s)" % (self, dataregion))

    # Case where the dataregion given overwrites this one totally,
    # inclusive of the end points.
    #            |-------|
    #         |=============|
    #            |=======|
    if ((dataregion.start <= self.start) and
        (dataregion.end >= self.end)):
      return DataRegion(dataregion.start,
                        dataregion.end,
                        dataregion.data)

    start_offset = dataregion.start - self.start
    end_offset = dataregion.end + 1 - self.start

    # Case where the dataregion is encapsulated entirely inside
    # this one, exclusive of the end points.
    #            |-------|
    #              |===|
    if ((dataregion.start > self.start) and
        (dataregion.end < self.end)):
      return DataRegion(self.start,
                        self.end,
                        (self.data[:start_offset] + 
                         dataregion.data +
                         self.data[end_offset:]))

    # Case where the dataregion is offset to the left and only
    # partially overwrites this one, inclusive of the end points,
    # and where it is adjacent.
    #            |-------|
    #         |======|
    #      |=====|
    #     |=====|
    if ((dataregion.start <= self.start) and
        (dataregion.end <= self.end)):
      return DataRegion(dataregion.start,
                        self.end,
                        dataregion.data + self.data[end_offset:])

    # Case where the dataregion is offset to the left and only
    # partially overwrites this one, inclusive of the end points.
    #            |-------|
    #                |======|
    #                    |======|
    #                     |======|
    if ((dataregion.start >= self.start) and
        (dataregion.end >= self.end)):
      return DataRegion(self.start,
                        dataregion.end,
                        self.data[:start_offset] + dataregion.data)

