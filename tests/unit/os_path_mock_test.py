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

'''Unit tests for the OS mocking module.'''

import os
import os.path
import sys
import unittest

sys.path.append('../../lib')
sys.path.append('lib')

import os_mock
import os_path_mock


class DirnameTest(unittest.TestCase):
  def setUp(self):
    pass

  def testAbsoluteDirname(self):
    self.assertEqual('/foo', os_path_mock.dirname('/foo/bar'))

  def testRelativeDirname(self):
    self.assertEqual('foo', os_path_mock.dirname('foo/bar'))


class BasenameTest(unittest.TestCase):
  def setUp(self):
    pass

  def testAbsoluteBasename(self):
    self.assertEqual('bar', os_path_mock.basename('/foo/bar'))

  def testRelativeBasename(self):
    self.assertEqual('bar', os_path_mock.basename('foo/bar'))


class IsfileTest(unittest.TestCase):
  def setUp(self):
    os_mock._filesystem = os_mock.FakeDir('')

    f    = os_mock.FakeFile('file')
    link = os_mock.FakeSymlink('link', '/file')
    d    = os_mock.FakeDir('dir')

    os_mock._filesystem.linkChild('file', f)
    os_mock._filesystem.linkChild('link', link)
    os_mock._filesystem.linkChild('dir',  d)

  def testIsFile(self):
    self.assertEqual(True, os_path_mock.isfile('/file'))
    self.assertEqual(True, os_path_mock.isfile('file'))

  def testIsntFile(self):
    self.assertEqual(False, os_path_mock.isfile('/dir'))
    self.assertEqual(False, os_path_mock.isfile('dir'))

    self.assertEqual(False, os_path_mock.isfile('/link'))
    self.assertEqual(False, os_path_mock.isfile('link'))


class IslinkTest(unittest.TestCase):
  def setUp(self):
    pass


class IsdirTest(unittest.TestCase):
  def setUp(self):
    pass


class JoinTest(unittest.TestCase):
  def setUp(self):
    pass


if __name__ == '__main__':
  unittest.main()
