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

import tsumufs


class ChangeSet(object):
  changes = []
  timestamp = None

  _VALID_TYPES = { 'patch':    [ 'start', 'end', 'data' ],
                   'truncate': [ 'pos' ],
                   'rename':   [ 'newname' ],
                   'unlink':   [ ],
                   'link':     [ 'newname' ] }

  def __init__(self, timestamp):
    self.changes = []
    self.timestamp = timestamp

  def addChange(self, type_, **kwargs):
    if type_ not in self._VALID_TYPES.keys():
      return False

    change = { 'type': type_ }
    for argname in self._VALID_TYPES[type_]:
      change[argname] = kwargs[argname]

    self.changes.extend(change)

  def _applyPatch(self, change):
    pass

  def _applyTruncate(self, change):
    pass

  def _applyRename(self, change):
    pass

  def _applyUnlink(self, change):
    pass

  def _applyLink(self, change):
    pass

  def applySet(self, filename):
    methods = {
      'patch': self._applyPatch,
      'truncate': self._applyTruncate,
      'rename': self._applyRename,
      'unlink': self._applyUnlink,
      'link': self._applyLink,
      }

    for change in self.changes:
      type_ = change['type']
      methods[type_].__call__(change)
