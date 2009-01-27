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
import tsumufs.dataregion as dataregion
import tsumufs.inodechange as inodechange


class InstanceCheck(unittest.TestCase):
  def setUp(self):
    pass

  def testInstanciation(self):
    inodechange.InodeChange()


class DataChangeCheck(unittest.TestCase):
  def setUp(self):
    self.change = inodechange.InodeChange()

  def testAddDataChange(self):
    self.change.addDataChange(0, 5, '0' * 5)
    result = self.change.getDataChanges()

    self.assertEqual(1, len(result))
    self.assertEqual('0' * 5, result[0].getData())
    self.assertEqual(0, result[0].getStart())
    self.assertEqual(5, result[0].getEnd())

  def testAddDataChangeFailure(self):
    self.assertRaises(dataregion.RangeError,
                      self.change.addDataChange, 5, 0, '0' * 5)
    self.assertRaises(dataregion.RegionLengthError,
                      self.change.addDataChange, 0, 0, '0' * 5)

  def testMergeMiddle(self):
    self.change.addDataChange(0, 1, '1')
    self.change.addDataChange(2, 3, '3')
    self.change.addDataChange(1, 2, '2')

    changes = self.change.getDataChanges()

    self.assertEqual(1, len(changes))
    self.assertEqual(0, changes[0].getStart())
    self.assertEqual(3, changes[0].getEnd())
    self.assertEqual(3, len(changes[0].getData()))
    self.assertEqual('123', changes[0].getData())

  def testReverseMerge(self):
    self.change.addDataChange(1, 2, '2')
    self.change.addDataChange(2, 3, '3')
    self.change.addDataChange(0, 1, '1')

    changes = self.change.getDataChanges()

    self.assertEqual(1, len(changes))
    self.assertEqual(0, changes[0].getStart())
    self.assertEqual(3, changes[0].getEnd())
    self.assertEqual(3, len(changes[0].getData()))
    self.assertEqual('123', changes[0].getData())

  def testOrderedMerge(self):
    self.change.addDataChange(0, 1, '1')
    self.change.addDataChange(1, 2, '2')
    self.change.addDataChange(2, 3, '3')

    changes = self.change.getDataChanges()

    self.assertEqual(1, len(changes))
    self.assertEqual(0, changes[0].getStart())
    self.assertEqual(3, changes[0].getEnd())
    self.assertEqual(3, len(changes[0].getData()))
    self.assertEqual('123', changes[0].getData())

  def testPartialMerge(self):
    self.change.addDataChange(0, 1, '1')
    self.change.addDataChange(2, 3, '3')
    self.change.addDataChange(4, 5, '5')
    self.change.addDataChange(3, 4, '4')

    changes = self.change.getDataChanges()
    self.assertEqual(2, len(changes))

    self.change.addDataChange(6, 7, '7')

    changes = self.change.getDataChanges()
    self.assertEqual(3, len(changes))

if __name__ == '__main__':
  unittest.main()
