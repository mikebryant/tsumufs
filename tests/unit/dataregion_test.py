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


class InstanceCheck(unittest.TestCase):
  def setUp(self):
    self.testData = '1' * 10

  def testInstanciation(self):
    r1 = dataregion.DataRegion(0, 10, self.testData)
    self.assertEqual(len(r1), len(self.testData))

  def testRegionLengthError(self):
    self.assertRaises(dataregion.RegionLengthError,
                      dataregion.DataRegion,
                      0, 1, self.testData)


class OverlapCheck(unittest.TestCase):
  def setUp(self):
    self.r1Start = 5
    self.r1End   = 10

    self.regionResults = [               # 012345678901234567890
      ('2' * 5),                         #      22222
      ('2' * 15),                        # 222222222222222
      ('1') + ('2' * 3) + ('1'),         #      12221
      ('2' * 5) + ('1' * 5),             # 2222211111
      ('2' * 6) + ('1' * 4),             # 2222221111
      ('2' * 8) + ('1' * 2),             # 2222222211
      ('2' * 10),                        # 2222222222
      ('2' * 10),                        #      2222222222
      ('1' * 2) + ('2' * 8),             #      1122222222
      ('1' * 4) + ('2' * 6),             #      1111222222
      ('1' * 5) + ('2' * 5)              #      1111122222
      ]

    self.overlappingRegions = [
      { 'start': 5,  'end': 10, 'type': 'perfect-overlap' },
      { 'start': 0,  'end': 15, 'type': 'outer-overlap'   },
      { 'start': 6,  'end': 9,  'type': 'inner-overlap'   },
      { 'start': 0,  'end': 5,  'type': 'left-adjacent'   },
      { 'start': 0,  'end': 6,  'type': 'left-overlap'    },  # overlap to left, exact on left
      { 'start': 0,  'end': 8,  'type': 'left-overlap'    },  # overlap to left
      { 'start': 0,  'end': 10, 'type': 'left-overlap'    },  # overlap to left, exact on right
      { 'start': 5,  'end': 15, 'type': 'right-overlap'   },  # overlap to right, exact on left
      { 'start': 7,  'end': 15, 'type': 'right-overlap'   },  # overlap to right
      { 'start': 9,  'end': 15, 'type': 'right-overlap'   },  # overlap to right, exact on right
      { 'start': 10, 'end': 15, 'type': 'right-adjacent'  }
      ]

  def testMergeTypes(self):
    for i in range(0, len(self.overlappingRegions)):
      testcase = self.overlappingRegions[i]
      result   = self.regionResults[i]

      r1 = dataregion.DataRegion(self.r1Start, self.r1End,
                                 '1' * (self.r1End - self.r1Start))
      r2 = dataregion.DataRegion(testcase['start'], testcase['end'],
                                 '2' * (testcase['end'] - testcase['start']))

      merge_type = r1.canMerge(r2)

      self.assertEqual(testcase['type'], merge_type)

  def testMerges(self):
    for i in range(0, len(self.overlappingRegions)):
      testcase = self.overlappingRegions[i]
      result   = self.regionResults[i]

      r1 = dataregion.DataRegion(self.r1Start, self.r1End,
                                 '1' * (self.r1End - self.r1Start))
      r2 = dataregion.DataRegion(testcase['start'], testcase['end'],
                                 '2' * (testcase['end'] - testcase['start']))

      r3 = r1.mergeWith(r2)

      self.assertEqual(result, r3.getData())

  def testRealCase(self):
    r1 = dataregion.DataRegion(1, 2, 'l')
    r2 = dataregion.DataRegion(2, 3, 'a')
    r3 = r1.mergeWith(r2)

    self.assertEqual(r3.getData(), 'la')
    self.assertEqual(r3.getStart(), 1)
    self.assertEqual(r3.getEnd(), 3)

  def testNonMergable(self):
    for testcase in self.overlappingRegions:
      r1 = dataregion.DataRegion(2000, 2001, '1')
      r2 = dataregion.DataRegion(testcase['start'], testcase['end'],
                                 '2' * (testcase['end'] - testcase['start']))

      self.assertEqual(None, r1.canMerge(r2))

if __name__ == '__main__':
  unittest.main()
