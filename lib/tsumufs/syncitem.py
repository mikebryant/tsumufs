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

import cPickle

from inodechange import *
from dataregion import *

import logging
logger = logging.getLogger(__name__)

import tsumufs


class SyncItem(object):
  '''
  Class that encapsulates a change to the filesystem in the SyncLog. Note that
  this does /not/ include DataRegions -- specifically that should be in a
  different list.
  '''

  _type = None        # 'new|'link|'unlink|'change|'rename

  _file_type = None   # 'file|'dir|'socket|'fifo|'device
  _dev_type  = None   # 'char|'block
  _major     = None   # integer
  _minor     = None   # integer

  _old_fname = None   # string
  _new_fname = None   # string
  _filename  = None   # string

  _inum = None        # inode number

  _hargs = None

  _REQUIRED_KEYS = {
    'new':    [ 'file_type', 'filename' ],
    'link':   [ 'filename', 'inum' ],
    'change': [ 'filename', 'inum' ],
    'unlink': [ 'filename' ],
    'rename': [ 'old_fname', 'new_fname', 'inum' ],
    }

  _VALID_TYPES      = [ 'new', 'link', 'unlink', 'change', 'rename' ]
  _VALID_FILE_TYPES = [ 'file', 'dir', 'symlink', 'socket', 'fifo', 'device' ]
  _VALID_DEV_TYPES  = [ 'char', 'block' ]

  def __init__(self, type_, **hargs):
    self._type = type_
    self._hargs = hargs

    if self._type not in self._VALID_TYPES:
      raise TypeError('Invalid change type %s' % self._type)

    for key in self._REQUIRED_KEYS[self._type]:
      if key not in hargs.keys():
        raise TypeError('Missing required key %s' % key)

    for key in hargs.keys():
      self.__dict__['_' + key] = hargs[key]

  def __str__(self):
    return (('<SyncItem:'
             ' type: %s'
             ' filename: %s'
             ' inum: %s>')
            % (self._type,
               self._filename,
               str(self._inum)))

  def __repr__(self):
    return str(self)

  def getType(self):
    return self._type

  def getFileType(self):
    return self._file_type

  def getMajor(self):
    return self._major

  def getMinor(self):
    return self._minor

  def getOldFilename(self):
    return self._old_fname

  def getNewFilename(self):
    return self._new_fname

  def getFilename(self):
    return self._filename

  def getInum(self):
    return self._inum
