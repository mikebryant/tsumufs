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
import posix

import tsumufs


class FilePermission(tsumufs.Debuggable):
  '''
  Class that mimics the file permissions of a file in the cache.

  File permissions include the following:
    - uid
    - gid
    - mode bits (aside from file types)
  '''

  uid = None
  gid = None
  mode = 0

  def __init__(self, statresult=None):
    if statresult != None:
      self.uid = statresult.st_uid
      self.gid = statresult.st_gid
      self.mode = statresult.st_mode

  def __str__(self):
    return '<FilePermission uid:%d gid:%d mode:%o' % (self.uid,
                                                      self.gid,
                                                      self.mode)

  def __repr__(self):
    return str(self)

  def overlayStatFromFile(self, realpath):
    result = tsumufs.MutableStat(os.lstat(realpath))

    result.st_uid = self.uid
    result.st_gid = self.gid
    result.st_mode = self.mode

    return result

  def overlayStatFromStat(self, stat_result):
    result = tsumufs.MutableStat(stat_result)

    result.st_uid = self.uid
    result.st_gid = self.gid
    result.st_mode = self.mode

    return result
