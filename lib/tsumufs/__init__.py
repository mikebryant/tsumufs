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
import pwd
import grp

# Not the greatest thing in the world to do, but it makes things
# organizationally easier to reach. Dumping all of these classes into this file
# directly would be impractical. In general, we follow the "one class one file"
# rule.

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
from syncitem import *
from mutablestat import *
from filepermission import *
from permissionsoverlay import *
from extendedattributes import *
from metrics import *


__version__ = (0, 11)

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
synclogPath = None

permsOverlay = None
permsPath = None

socketDir = '/var/run/tsumufs'

unmounted       = threading.Event()
nfsAvailable    = threading.Event()
forceDisconnect = threading.Event()
syncPause       = threading.Event()

defaultCacheMode = 0600         # readable only by the user

checkpointTimeout = 30          # in seconds

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

  syslog.syslog(syslog.LOG_ERR, '*** Unhandled exception occurred')
  syslog.syslog(syslog.LOG_ERR, '***     Type: %s' % str(type))
  syslog.syslog(syslog.LOG_ERR, '***    Value: %s' % str(value))
  syslog.syslog(syslog.LOG_ERR, '*** Traceback:')

  for line in traceback.extract_tb(tb):
    syslog.syslog(syslog.LOG_ERR, '***    %s(%d) in %s: %s'
                  % line)


def nfsPathOf(fusepath):
  '''
  Quick one-off method to help with translating FUSE-side pathnames
  to VFS pathnames.

  Returns:
  A string containing the absolute path to the file on the NFS
  mount.

  Raises:
  Nothing
  '''

  # Catch the case that the fusepath is absolute (which it should be)
  if fusepath[0] == '/':
    rhs = fusepath[1:]
  else:
    rhs = fusepath

  transpath = os.path.join(tsumufs.nfsMountPoint, rhs)
  return transpath


def cachePathOf(fusepath):
  '''
  Quick one-off method to help with translating FUSE-side pathnames
  to VFS pathnames.

  This method returns the cache-side VFS pathname for the given
  fusepath.

  Returns:
  A string containing the absolute path to the file on the cache
  point.

  Raises:
  Nothing
  '''

  # Catch the case that the fusepath is absolute (which it should be)
  if fusepath[0] == '/':
    rhs = fusepath[1:]
  else:
    rhs = fusepath

  transpath = os.path.join(tsumufs.cachePoint, rhs)
  return transpath


def getGidsForUid(uid):
  '''
  Return a listing of group IDs that the given uid belongs to. Note that the
  primary group is included in this list.

  Returns:
    A list of integers.

  Raises:
    Nothing.
  '''

  pwent = pwd.getpwuid(uid)
  username = pwent.pw_name
  groups = [ pwent.pw_gid ]

  for group in grp.getgrall():
    if username in group.gr_mem:
      groups.append(group.gr_gid)

  return groups
