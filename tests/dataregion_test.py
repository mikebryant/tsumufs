#!/usr/bin/python2.4
#
# Copyright 2007 Google, Inc. All Rights Reserved.

"""Unit tests for the DataRegion class."""

import unittest
import tsumufs.dataregion as dataregion

class InstanceCheck(unittest.TestCase):
  def setUp(self):
    self.testData = "1" * 10

  def testInstanciation(self):
    r1 = dataregion.DataRegion(0, 9, self.testData)
    self.assertEqual(len(r1), len(self.testData))

  def testRegionLengthError(self):
    self.assertRaises(dataregion.RegionLengthError,
                      dataregion.DataRegion(0, 1, self.testData))

class OverlapCheck(unittest.TestCase):
  def setUp(self):
    self.r1 = None
    self.r1Start = 10
    self.r1End   = 100
    self.overlappingRegions = [
      { "start": 50,  "end": 150 },  # overlap to right
      { "start": 10,  "end": 100 },  # exact overlap
      { "start": 0,   "end": 150 },  # complete overlap
      { "start": 10,  "end": 50 },   # overlap to left, exact on left
      { "start": 50,  "end": 100},   # overlap to right, exact on right
      { "start": 100, "end": 1000},  # overlap to right, 
      ]

    self.r1 = dataregion.DataRegion(self.r1Start,
                                    self.r1End,
                                    "1" * (self.r1End - self.r1Start))

if __name__ == "__main__":
  unittest.main()
