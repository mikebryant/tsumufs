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

"""TsumuFS, a NFS-based caching filesystem."""

import threading

from triumvirate import *
from nfsmount import *
from synclog import *
from fusethread import *
from syncthread import *
from mountthread import *

__version__ = (0, 0, 1)

debugMode = False

progName = None

mountSource  = None
mountPoint   = None
mountOptions = None

nfsBaseDir    = "/var/lib/tsumufs/nfs"
nfsMountPoint = None

cacheBaseDir  = "/var/cache/tsumufs"
cacheSpecDir  = "/var/lib/tsumufs/cachespec"
cachePoint    = None

unmountedEvent    = threading.Event()
nfsConnectedEvent = threading.Event()

nfsMount = None
