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

import traceback
import syslog

import fuse
from fuse import Fuse

import tsumufs


class ExtendedAttributes(tsumufs.Debuggable):
  '''
  This class represents the ability to store TsumuFS specific extended attribute
  data for various file types and paths.
  '''

  _attributeCallbacks = { 'root': {},
                          'dir': {},
                          'file': {} }

  @classmethod
  def _validateXAttrType(cls, type_):
    if type_ not in cls._attributeCallbacks.keys():
      raise KeyError('Extended attribute type %s is not one of %s' %
                     (type_, cls._attributeCallbacks.keys()))

  @classmethod
  def _validateName(cls, name):
    if not name.startswith('tsumufs.'):
      name = 'tsumufs.%s' % name

    return name

  @classmethod
  def setCallbackFor(cls, type_, name, set_callback, get_callback):
    cls._validateXAttrType(type_)
    name = cls._validateName(name)

    cls._attributeCallbacks[type_][name] = { 'set': set_callback,
                                             'get': get_callback }

  @classmethod
  def clearCallbackFor(cls, type_, name):
    cls._validateXAttrType(type_)
    name = cls._validateName(name)

    if cls._attributeCallbacks.has_key(type_):
      del cls._attributeCallbacks[type_][name]

  @classmethod
  def clearAllCallbacks(cls):
    _attributeCallbacks = { 'root': {},
                            'dir': {},
                            'file': {} }


  @classmethod
  def getXAttr(cls, type_, path, name):
    cls._validateXAttrType(type_)
    name = cls._validateName(name)

    if cls._attributeCallbacks.has_key(type_):
      callback = cls._attributeCallbacks[type_][name]['get']
      return callback(type_, path)

    raise KeyError('No extended attribute set for (%s, %s) pair.' %
                   (type_, name))

  @classmethod
  def getAllXAttrs(cls, type_, path):
    cls._validateXAttrType(type_)
    results = {}

    if cls._attributeCallbacks.has_key(type_):
      for name in cls._attributeCallbacks[type_]:
        callback = cls._attributeCallbacks[type_][name]['get']
        results[name] = callback(type_, path)

    return results

  @classmethod
  def setXAttr(cls, type_, path, name, value):
    cls._validateXAttrType(type_)
    name = cls._validateName(name)

    if cls._attributeCallbacks.has_key(type_):
      callback = cls._attributeCallbacks[type_][name]['set']
      return callback(type_, path, value)

    raise KeyError('No extended attribute set for (%s, %s) pair.' %
                   (type_, name))
