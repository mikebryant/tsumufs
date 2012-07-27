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
import logging
logger = logging.getLogger(__name__)

import fuse
from fuse import Fuse

import tsumufs


class ExtendedAttributes(object):
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
      if type_ == 'any':
        return

      raise KeyError('Extended attribute type %s is not one of %s' %
                     (type_, cls._attributeCallbacks.keys()))

  @classmethod
  def setCallbackFor(cls, type_, name, set_callback, get_callback):
    cls._validateXAttrType(type_)

    if type_ == 'any':
      types = cls._attributeCallbacks.keys()
    else:
      types = [ type_ ]

    for type_ in types:
      cls._attributeCallbacks[type_][name] = { 'set': set_callback,
                                               'get': get_callback }

  @classmethod
  def clearCallbackFor(cls, type_, name):
    cls._validateXAttrType(type_)

    if type_ == 'any':
      type_ = cls._attributeCallbacks.keys()
    else:
      type_ = [ type_ ]

    for type_ in cls._attributeCallbacks.keys():
      if cls._attributeCallbacks.has_key(type_):
        del cls._attributeCallbacks[type_][name]

  @classmethod
  def clearAllCallbacks(cls):
    cls._attributeCallbacks = { 'root': {},
                                'dir': {},
                                'file': {} }

  @classmethod
  def getXAttr(cls, type_, path, name):
    cls._validateXAttrType(type_)

    if cls._attributeCallbacks.has_key(type_):
      callback = cls._attributeCallbacks[type_][name]['get']

      try:
        return callback.__call__(type_, path)
      except Exception, e:
        result  = '*** Unhandled exception occurred\n'
        result += '***     Type: %s\n' % str(e.__class__)
        result += '***    Value: %s\n' % str(e)
        result += '*** Traceback:\n'

        tb = traceback.extract_stack()
        for line in tb:
          result += '***    %s(%d) in %s: %s\n' % line

        return result

    raise KeyError('No extended attribute set for (%s, %s) pair.' %
                   (type_, name))

  @classmethod
  def getAllXAttrs(cls, type_, path):
    cls._validateXAttrType(type_)
    results = {}

    if cls._attributeCallbacks.has_key(type_):
      for name in cls._attributeCallbacks[type_]:
        callback = cls._attributeCallbacks[type_][name]['get']
        results[name] = callback.__call__(type_, path)

    return results

  @classmethod
  def getAllNames(cls, type_):
    cls._validateXAttrType(type_)
    results = []

    if cls._attributeCallbacks.has_key(type_):
      results = cls._attributeCallbacks[type_].keys()

    return results

  @classmethod
  def setXAttr(cls, type_, path, name, value):
    cls._validateXAttrType(type_)

    if cls._attributeCallbacks.has_key(type_):
      callback = cls._attributeCallbacks[type_][name]['set']
      return callback.__call__(type_, path, value)

    raise KeyError('No extended attribute set for (%s, %s) pair.' %
                   (type_, name))


def extendedattribute(type_, name):
  def decorator(func):
    def wrapper(__self, *args, **kwargs):
      return func(__self, *args, **kwargs)

    ExtendedAttributes.setCallbackFor(type_, name, wrapper, wrapper)
    return wrapper
  return decorator
