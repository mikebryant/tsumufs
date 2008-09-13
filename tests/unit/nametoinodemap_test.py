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
import tsumufs


class NameToInodeCheck(unittest.TestCase):
  def setUp(self):
    tsumufs.NameToInodeMap.invalidate()
    tsumufs.NameToInodeMap.setNameToInode('single-name-to-inode', 1111)
    tsumufs.NameToInodeMap.setInodeToName(2222, 'single-inode-to-name')

    tsumufs.NameToInodeMap.setNameToInode('double-name-to-inode',     3333)
    tsumufs.NameToInodeMap.setNameToInode('double-name-to-inode-two', 3333)

  def testSingleNameToInode(self):
    self.assertEqual(1111,
                     tsumufs.NameToInodeMap.nameToInode('single-name-to-inode'))
    self.assertEqual(['single-name-to-inode'],
                     tsumufs.NameToInodeMap.inodeToName(1111))

  def testSingleInodeToName(self):
    self.assertEqual(2222,
                     tsumufs.NameToInodeMap.nameToInode('single-inode-to-name'))
    self.assertEqual(['single-inode-to-name'],
                     tsumufs.NameToInodeMap.inodeToName(2222))

  def testDoubleNameToInode(self):
    self.assertEqual(3333,
                     tsumufs.NameToInodeMap.nameToInode('double-name-to-inode'))
    self.assertEqual(3333,
                     tsumufs.NameToInodeMap.nameToInode('double-name-to-inode-two'))
    self.assertEqual(['double-name-to-inode', 'double-name-to-inode-two'],
                     tsumufs.NameToInodeMap.inodeToName(3333))


if __name__ == '__main__':
  unittest.main()
