#!/usr/bin/python2.4
# -*- python -*-
#
# Copyright (C) 2007  Google, Inc. All Rights Reserved.
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

'''Unit tests for the DataRegion class.'''

import sys

sys.path.append('../lib')
sys.path.append('lib')

import unittest
from tsumufs.extendedattributes import ExtendedAttributes


def _set_callback(type_, path, value):
  return (type_, path, value)


def _get_callback(type_, path):
  return (type_, path)


class SetTest(unittest.TestCase):
  def setUp(self):
    ExtendedAttributes.clearAllCallbacks()

  def testValidRootCallback(self):
    ExtendedAttributes.setCallbackFor('root', 'test',
                                     _set_callback, _get_callback)
    result = ExtendedAttributes.getXAttr('root', '/', 'test')

    self.assertEquals(result[0], 'root')
    self.assertEquals(result[1], '/')

    result = ExtendedAttributes.setXAttr('root', '/', 'test', 'value')

    self.assertEquals(result[0], 'root')
    self.assertEquals(result[1], '/')
    self.assertEquals(result[2], 'value')


class GetAllTest(unittest.TestCase):
  def setUp(self):
    ExtendedAttributes.clearAllCallbacks()
    ExtendedAttributes.setCallbackFor('root', 'test',
                                     _set_callback, _get_callback)
    ExtendedAttributes.setCallbackFor('dir', 'test2',
                                     _set_callback, _get_callback)

  def testGetAll(self):
    result = ExtendedAttributes.getAllXAttrs('root', '/')
    self.assertEquals({ 'tsumufs.test': ('root', '/') }, result)

    result = ExtendedAttributes.getAllXAttrs('dir', '/')
    self.assertEquals({ 'tsumufs.test2': ('dir', '/') }, result)


class InvalidGetTest(unittest.TestCase):
  def setUp(self):
    ExtendedAttributes.clearAllCallbacks()

  def testGetInvalidXattr(self):
    self.assertRaises(KeyError, ExtendedAttributes.getXAttr,
                      'root', '/', 'thisvalueshouldntexistever')


if __name__ == '__main__':
  unittest.main()
