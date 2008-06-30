#!/usr/bin/python2.4
#
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

import os
import sys
import time
import threading
import Queue


class SyncQueue(object):
  '''
  '''

  _queue = []
  _lock  = threading.Condition()

  def acquire(self, block=1):
    return self._lock.acquire(block)

  def release(self):
    return self._lock.release()

  def flushToDisk(self):
    self.acquire()

    try:
      pass

    finally:
      self.release()

  def loadFromDisk(self):
    self.acquire()

    try:
      pass

    finally:
      self.release()

  def validate(self):
    self.acquire()

    try:
      pass

    finally:
      self.release()

  def peek(self):
    self.acquire()

    try:
      if len(self._queue) == 0:
        raise Queue.Empty('Nothing in the queue.')

      item = self._queue[-1]
      return item

    finally:
      self.release()

  def remove(self, item):
    self.acquire()

    try:
      found = False

      if len(self._queue) == 0:
        raise Queue.Empty('Nothing in the queue.')

      for i in range(len(self._queue), -1, -1):
        if self._queue[i] == item:
          found = True

          if i == len(self._queue):
            self._queue = self._queue[:-1]
          elif i == 0:
            self._queue = self._queue[1:]
          else:
            self._queue = self._queue[:i] + self._queue[i+1:]


      if not found:
        raise Queue.Empty('Item not found.')
      else:
        return True

    finally:
      self.release()

  def put(self, item):
    self.acquire()

    try:
      self._queue.append(item)

    finally:
      self.release()
