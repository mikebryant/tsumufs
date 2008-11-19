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

import threading

from debuggable import *
from triumvirate import *
from cachemanager import *
from nfsmount import *
from synclog import *
from fusefile import *
from fusethread import *
from syncthread import *
from inodechange import *
from nametoinodemap import *


__version__ = (0, 9)

debugMode = False

progName   = None
syslogOpen = False

mountSource  = None
mountPoint   = None
mountOptions = None

nfsBaseDir    = '/var/lib/tsumufs/nfs'
nfsMountPoint = None
nfsMount      = None

cacheBaseDir = '/var/cache/tsumufs'
cacheSpecDir = '/var/lib/tsumufs/cachespec'
cachePoint   = None
cacheManager = None

syncLog = None

socketDir = '/var/run/tsumufs'

unmounted       = threading.Event()
nfsAvailable    = threading.Event()
forceDisconnect = threading.Event()
syncPause       = threading.Event()


def syslogCurrentException():
  '''
  Shortcut to the below idiom.
  '''

  syslogExceptHook(*sys.exc_info())


def syslogExceptHook(type, value, tb):
  '''
  Quick exception handler to log exceptions to syslog rather than
  dumping them to /dev/null after FUSE has forked.
  '''

  syslog.syslog('*** Unhandled exception occurred')
  syslog.syslog('***     Type: %s' % str(type))
  syslog.syslog('***    Value: %s' % str(value))
  syslog.syslog('*** Traceback:')

  for line in traceback.extract_tb(tb):
    syslog.syslog('***    %s(%d) in %s: %s'
                  % line)
