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
import posix

import tsumufs

class MutableStat(object):
  '''
  Placeholder object to represent a stat that is directly mutable.
  '''

  n_fields = 0
  n_sequence_fields = 0
  n_unnamed_fields = 0
  st_atime = None
  st_blksize = 0
  st_blocks = 0
  st_ctime = None
  st_dev = 0
  st_gid = 0
  st_ino = 0
  st_mode = 0
  st_mtime = None
  st_nlink = 0
  st_rdev = 0
  st_size = 0L
  st_uid = 0

  _keys = [ 'st_mode', 'st_ino', 'st_dev', 'st_nlink', 'st_uid', 'st_gid',
            'st_size', 'st_atime', 'st_mtime', 'st_ctime' ]

  def __init__(self, stat_result):
    for key in dir(stat_result):
      if not key.startswith('_'):
        self.__dict__[key] = stat_result.__getattribute__(key)

  def __getitem__(self, idx):
    key = self._keys[idx]
    return self.__dict__[key]

  def __getslice__(self, start, end):
    result = []

    for key in self._keys[start:end]:
      result.append(self.__dict__[key])

    return tuple(result)

  def __repr__(self):
    return repr(self[0:len(self._keys)])
