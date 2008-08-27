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

class RangeError(Exception):
  '''
  Exception for representing a range error.
  '''

  pass

class RegionError(Exception):
  '''
  Exception to signal when a general region error has occured.
  '''

  pass

class RegionLengthError(RegionError):
  '''
  Exception to signal when a region length does not match it's
  range.
  '''

  pass

class RegionOverlapError(RegionError):
  '''
  Exception to signal when a region overlap error has
  occurred. Typically when a DataRegion::mergeWith call has been made
  with the argument being a region that cannot be merged.
  '''

  pass

class DataRegion(object):
  '''
  Class that represents a region of data in a file.

  This class is specifically used for managing the changes in files as
  stored in the cache on disk.
  '''

  _data   = None
  _start  = 0
  _end    = 0
  _length = 0

  def getData(self):
    '''
    Return the data that this object contains.

    Returns:
      String

    Raises:
      Nothing
    '''

    return self._data

  def getStart(self):
    '''
    Return the start offset of the region in the file it represents.

    Returns:
      Integer

    Raises:
      Nothing
    '''

    return self._start

  def getEnd(self):
    '''
    Return the end offset of the region in the file it represents.

    Returns:
      Integer

    Raises:
      Nothing
    '''
    return self._end

  def __len__(self):
    '''
    Return the length of the region.

    Returns:
      Integer

    Raises:
      None
    '''

    return self._length

  def __repr__(self):
    '''
    Method to display a somewhat transparent representation of a
    DataRegion object.
    '''

    return('<DataRegion [%d:%d] (%d): "%s">'
           % (self._start, self._end, self._length, self._data))

  def __init__(self, start, end, data):
    '''
    Initializer. Can raise InvalidRegionSpecifiedError and
    RegionDoesNotMatchLengthError.
    '''

    if (end < start):
      raise RangeError, ('End of range is before start (%d, %d)'
                         % (start, end))

    if ((end - start + 1) != len(data)):
      raise RegionLengthError, ('Range specified does not match '
                                'the length of the data given.')

    self._start = start
    self._end = end
    self._data = data
    self._length = len(data)

  def canMerge(self, dataregion):
    if ((dataregion.start > self._end) or       #       |-----|
        (dataregion.end < self._start)):        # |====|
      if ((self._end + 1 == dataregion.start) or
          (dataregion.end + 1 == self._start)):
        return True
      else:
        return False
    elif ((dataregion.start >= self._start) and #    |-----|
          (dataregion.start <= self._end)):     #       |=====|
      return True
    elif ((dataregion.end >= self._start) and   #    |-----|
          (dataregion.end <= self._end)):       # |=====|
      return True
    elif ((dataregion.start < self._start) and  #    |-----|
          (dataregion.end > self._end)):        # |===========|
      return True

  def mergeWith(self, dataregion):
    '''
    Attempt to merge the given DataRegion into the current
    instance. Raises RegionError if the given DataRegion does not
    overlap with the self.
    '''

    if (not self.canMerge(dataregion)):
      # Catch the invalid case where the region doesn't overlap
      # or is not adjacent.
      raise RegionOverlapError, (('The DataRegion given does not '
                                  'overlap this instance '
                                  '(%s, %s)') % (self, dataregion))

    # Case where the dataregion given overwrites this one totally,
    # inclusive of the end points.
    #            |-------|
    #         |=============|
    #            |=======|
    if ((dataregion.start <= self._start) and
        (dataregion.end >= self._end)):
      return DataRegion(dataregion.start,
                        dataregion.end,
                        dataregion.data)

    start_offset = dataregion.start - self._start
    end_offset = dataregion.end + 1 - self._start

    # Case where the dataregion is encapsulated entirely inside
    # this one, exclusive of the end points.
    #            |-------|
    #              |===|
    if ((dataregion.start > self._start) and
        (dataregion.end < self._end)):
      return DataRegion(self._start,
                        self._end,
                        (self._data[:start_offset] +
                         dataregion.data +
                         self._data[end_offset:]))

    # Case where the dataregion is offset to the left and only
    # partially overwrites this one, inclusive of the end points,
    # and where it is adjacent.
    #            |-------|
    #         |======|
    #      |=====|
    #     |=====|
    if ((dataregion.start <= self._start) and
        (dataregion.end <= self._end)):
      return DataRegion(dataregion.start,
                        self._end,
                        dataregion.data + self._data[end_offset:])

    # Case where the dataregion is offset to the left and only
    # partially overwrites this one, inclusive of the end points.
    #            |-------|
    #                |======|
    #                    |======|
    #                     |======|
    if ((dataregion.start >= self._start) and
        (dataregion.end >= self._end)):
      return DataRegion(self._start,
                        dataregion.end,
                        self._data[:start_offset] + dataregion.data)

