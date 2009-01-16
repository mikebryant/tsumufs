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

    return('<DataRegion [%d:%d] (%d): %s>'
           % (self._start, self._end, self._length, repr(self._data)))

  def __init__(self, start, end, data):
    '''
    Initializer. Can raise InvalidRegionSpecifiedError and
    RegionDoesNotMatchLengthError.
    '''

    if (end < start):
      raise RangeError, ('End of range is before start (%d, %d)'
                         % (start, end))

    if ((end - start) != len(data)):
      raise RegionLengthError, (('Range specified (%d-%d) does not match '
                                 'the length of the data (%d) given (%s).')
                                % (start, end, len(data), repr(data)))

    self._start = start
    self._end = end
    self._data = data
    self._length = len(data)

  def canMerge(self, dataregion):
    if ((dataregion._start == self._start) and   # |---|
        (dataregion._end == self._end)):         # |===|
      return 'perfect-overlap'

    elif ((dataregion._start < self._start) and  #       |-----|
          (dataregion._end == self._start)):     # |====|
      return 'left-adjacent'

    elif ((dataregion._end > self._end) and      # |----|
          (dataregion._start == self._end)):     #       |=====|
      return 'right-adjacent'

    elif ((dataregion._start > self._start) and  # |-----------|
          (dataregion._end < self._end)):        #    |=====|
      return 'inner-overlap'

    elif ((dataregion._start < self._start) and  #    |-----|
          (dataregion._end > self._end)):        # |===========|
      return 'outer-overlap'

    elif ((dataregion._end >= self._start) and   #    |-----|
          (dataregion._end <= self._end) and     # |=====|
          (dataregion._start <= self._start)):   # |==|
      return 'left-overlap'                      # |========|

    elif ((dataregion._start >= self._start) and #    |-----|
          (dataregion._start <= self._end) and   #       |=====|
          (dataregion._end >= self._end)):       #          |==|
      return 'right-overlap'                     #    |========|

    else:
      return None

  def mergeWith(self, dataregion):
    '''
    Attempt to merge the given DataRegion into the current
    instance. Raises RegionError if the given DataRegion does not
    overlap with the self.
    '''

    merge_type = self.canMerge(dataregion)

    # Catch the invalid case where the region doesn't overlap
    # or is not adjacent.
    if merge_type == None:
      raise RegionOverlapError, (('The DataRegion given does not '
                                  'overlap this instance '
                                  '(%s, %s)') % (self, dataregion))

    # |===========|
    #    |-----|
    if merge_type in ('outer-overlap', 'perfect-overlap'):
      return dataregion

    # |-----------|
    #    |=====|
    elif merge_type == 'inner-overlap':
      start_offset = dataregion._start - self._start
      end_offset = self._length - (self._end - dataregion._end)

      return DataRegion(self._start, self._end,
                        (self._data[:start_offset] +
                         dataregion._data +
                         self._data[end_offset:]))

    # Case where the dataregion is offset to the left and only
    # partially overwrites this one, inclusive of the end points.
    #            |-------|
    #         |======|
    #      |=====|
    elif merge_type == 'left-overlap':
      start_offset = dataregion._end - self._start
      return DataRegion(dataregion._start, self._end,
                        dataregion._data + self._data[start_offset:])

    # Case where the dataregion is offset to the left and only
    # partially overwrites this one, inclusive of the end points.
    #            |-------|
    #                |======|
    #                    |======|
    elif merge_type in 'right-overlap':
      end_offset = self._length - (self._end - dataregion._start)
      return DataRegion(self._start, dataregion._end,
                        self._data[:end_offset] + dataregion._data)

    # Case where the dataregion is adjacent to the left.
    #            |-------|
    #     |=====|
    elif merge_type == 'left-adjacent':
      return DataRegion(dataregion._start, self._end,
                        dataregion._data + self._data)

    # Case where the dataregion is adjacent to the right.
    #            |-------|
    #                     |======|
    elif merge_type == 'right-adjacent':
      return DataRegion(self._start, dataregion._end,
                        self._data + dataregion._data)
