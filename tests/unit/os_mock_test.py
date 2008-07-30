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


class AccessTest(unittest.TestCase):
  _modes = [
                                  # R W X
    0,                            # 0 0 0
    os.X_OK,                      # 0 0 1
    os.W_OK | os.X_OK,            # 0 1 1
    os.W_OK,                      # 0 1 0
    os.R_OK | os.W_OK,            # 1 1 0
    os.R_OK,                      # 1 0 0
    os.R_OK | os.X_OK,            # 1 0 1
    os.R_OK | os.W_OK | os.X_OK,  # 1 1 1
    ]

  def setUp(self):
    os_mock._filesystem = FakeDir('')
    os_mock._cwd = '/'
    os_mock._euid = 0
    os_mock._egid = 0
    os_mock._egroups = [0]

  def testEnoent(self):
    pass

  def testModes(self):
    pass


class ChmodTest(unittest.TestCase):
  def setUp(self):
    os_mock._filesystem = FakeDir('')
    os_mock._cwd = '/'
    os_mock._euid = 0
    os_mock._egid = 0
    os_mock._egroups = [0]

  def testEnoent(self):
    os_mock.chmod

class ChownTest(unittest.TestCase):
  def setUp(self):
    pass


class CloseTest(unittest.TestCase):
  def setUp(self):
    pass


class FdopenTest(unittest.TestCase):
  def setUp(self):
    pass


class FtruncateTest(unittest.TestCase):
  def setUp(self):
    pass


class GetcwdTest(unittest.TestCase):
  def setUp(self):
    pass


class LchownTest(unittest.TestCase):
  def setUp(self):
    pass


class LinkTest(unittest.TestCase):
  def setUp(self):
    pass


class ListdirTest(unittest.TestCase):
  def setUp(self):
    pass


class LstatTest(unittest.TestCase):
  def setUp(self):
    pass


class MkdirTest(unittest.TestCase):
  def setUp(self):
    pass


class MknodTest(unittest.TestCase):
  def setUp(self):
    pass


class OpenTest(unittest.TestCase):
  def setUp(self):
    pass


class ReadlinkTest(unittest.TestCase):
  def setUp(self):
    pass


class RenameTest(unittest.TestCase):
  def setUp(self):
    pass


class RmdirTest(unittest.TestCase):
  def setUp(self):
    pass


class StatTest(unittest.TestCase):
  def setUp(self):
    pass


class StatvfsTest(unittest.TestCase):
  def setUp(self):
    pass


class StrerrorTest(unittest.TestCase):
  def setUp(self):
    pass


class SymlinkTest(unittest.TestCase):
  def setUp(self):
    pass


class SystemTest(unittest.TestCase):
  def setUp(self):
    pass


class UnlinkTest(unittest.TestCase):
  def setUp(self):
    pass


class UtimeTest(unittest.TestCase):
  def setUp(self):
    pass


if __name__ == '__main__':
  unittest.main()
