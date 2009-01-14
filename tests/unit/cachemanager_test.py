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

import os_mock as os

class InstanceCheck(unittest.TestCase):
  def testInstanciation(self):
    cm = tsumufs.CacheManager()


class CacheOpcodeCheck(unittest.TestCase):
  _test_states = [
    {'cached': False,
     'nfs-avail': False,
     'opcodes': ['enoent']},

    {'cached': False,
     'should-cache': False,
     'nfs-avail': True,
     'opcodes': ['use-nfs']},

    {'cached': False,
     'should-cache': True,
     'nfs-avail': True,
     'opcodes': ['cache', 'use-nfs']},

    {'cached': True,
     'should-cache': False,
     'nfs-avail': False,
     'opcodes': ['remove', 'enoent']},

    {'cached': True,
     'should-cache': False,
     'nfs-avail': True,
     'opcodes': ['remove', 'use-nfs']},

    {'cached': True,
     'should-cache': True,
     'nfs-avil': False,
     'opcodes': ['use-cached']},

    {'cached': True,
     'should-cache': True,
     'nfs-avail': True,
     'nfs-changed': False,
     'opcodes': ['use-cached']},

    {'cached': True,
     'should-cache': True,
     'cache-dirty': False,
     'nfs-avail': True,
     'nfs-changed': True,
     'opcodes': ['cache', 'use-cached']},

    {'cached': True,
     'should-cache': True,
     'cache-dirty': True,
     'nfs-avail': True,
     'nfs-changed': True,
     'opcodes': ['merge-conflict']}]

  def setUp(self):
    tsumufs.mountPoint    = '/tmp/tsumufs-mountpoint'
    tsumufs.nfsMountPoint = '/tmp/tsumufs-nfsmount'
    tsumufs.cachePoint    = '/tmp/tsumufs-cachepoint'


if __name__ == '__main__':
  unittest.main()
