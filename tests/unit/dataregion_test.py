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
    r1 = dataregion.DataRegion(0, 9, self.testData)
    self.assertEqual(len(r1), len(self.testData))

  def testRegionLengthError(self):
    self.assertRaises(dataregion.RegionLengthError,
                      dataregion.DataRegion,
                      0, 1, self.testData)


class OverlapCheck(unittest.TestCase):
  def setUp(self):
    self.r1 = None
    self.r1Start = 10
    self.r1End   = 100
    self.overlappingRegions = [
      { 'start': 50,  'end': 150 },  # overlap to right
      { 'start': 10,  'end': 100 },  # exact overlap
      { 'start': 0,   'end': 150 },  # complete overlap
      { 'start': 10,  'end': 50 },   # overlap to left, exact on left
      { 'start': 50,  'end': 100},   # overlap to right, exact on right
      { 'start': 100, 'end': 1000},  # overlap to right,
      ]

    self.r1 = dataregion.DataRegion(self.r1Start,
                                    self.r1End,
                                    '1' * (self.r1End - self.r1Start))


if __name__ == '__main__':
  unittest.main()
