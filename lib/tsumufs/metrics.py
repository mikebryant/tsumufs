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

import time
import threading

from extendedattributes import extendedattribute


_metrics_lock = threading.RLock()
_metrics = {}


def benchmark(func):
  '''
  Decorator method to help gather metrics.
  '''

  global _metrics

  def wrapper(*__args, **__kwargs):
    name = func.__name__

    start_time = time.time()
    result = func.__call__(*__args, **__kwargs)
    delta_t = time.time() - start_time

    try:
      _metrics_lock.acquire()

      if not _metrics.has_key(name):
        _metrics[name] = [ 1, delta_t ]
      else:
        _metrics[name][0] += 1
        _metrics[name][1] += delta_t

    finally:
      _metrics_lock.release()

    return result
  return wrapper


@extendedattribute('root', 'tsumufs.metrics')
def xattr_metrics(type_, path, value=None):
  global _metrics

  if value:
    return -errno.EOPNOTSUPP

  try:
    _metrics_lock.acquire()

    if len(_metrics.keys()) == 0:
      return '{}'

    result = '{ '
    for name in _metrics.keys():
      result += ("'%s': %f (%d), " %
                 (name, _metrics[name][1] / _metrics[name][0],
                  _metrics[name][0]))

    result = result[:-2]
    result += ' }'

    return result

  finally:
    _metrics_lock.release()
