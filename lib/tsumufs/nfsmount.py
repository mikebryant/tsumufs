#!/usr/bin/python2.4
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

"""TsumuFS, a NFS-based caching filesystem.

Blah blah.
"""

__author__ = 'jtgans@google.com (June Tate-Gans)'

import os
from errno import *
from stat import *

from threading import Event

class NFSMount(object):
  """Represents the NFS mount iself.

  This object is responsible for accessing files and data in the NFS
  mount. It is also responsible for setting the connectedEvent to
  False in case of an NFS access error."""

  mountSource = None
  mountPoint = None
  mountOptions = None

  connectedEvent = Event()

  def __init__(self, mountSource, mountPoint, mountOptions):
    self.mountPoint = mountPoint
    self.mountSource = mountSource
    self.mountOptions = mountOptions

  def lockFile(self, filename):
    """Method to lock a file. Blocks if the file is already locked.

    Args:
      filename: The complete pathname to the file to lock.

    Returns:
      A boolean value.
    """
    pass

  def unlockFile(self, filename):
    """Method to unlock a file.

    Args:
      filename: The complete pathname to the file to unlock.

    Returns:
      A boolean value.
    """
    pass

  def pingServerOK(self):
    """Method to verify that the NFS server is available.
    """
    pass

  def nfsCheckOK(self):
    """Method to verify that the NFS server is available and returning
    valid responses.
    """
    pass

  def readFileRegion(self, filename, start, end):
    """Method to read a region of a file from the NFS
    mount. Additionally adds the inode to filename mapping to the
    InodeMap singleton.

    Args:
      filename: the complete pathname to the file to read from.
      start: the beginning offset to read from.
      end: the ending offset to read from.

    Returns:
      A string containing the data read.

    Raises:
      NFSMountError: An error occurred during an NFS call.
      RangeError: The start and end provided are invalid.
      IOError: Usually relating to permissions issues on the file.
    """
    pass

  def writeFileRegion(self, filename, start, end, data):
    """Method to write a region to a file on the NFS
    mount. Additionally adds the resulting inode to filename mapping
    to the InodeMap singleton.

    Args:
      filename: the complete pathname to the file to write to.
      start: the beginning offset to write to.
      end: the ending offset to write to.
      data: the data to write.

    Raises:
      NFSMountError: An error occurred during an NFS call.
      RangeError: The start and end provided are invalid.
      IOError: Usually relating to permissions on the file.
    """
    pass

  def mount(self):
    """Quick and dirty method to actually mount the real NFS connection
    somewhere else on the filesystem. For now, this just shells out to
    the mount(8) command to do its dirty work.
    """

    # Setup any additional mount options we need
    mount_opts = "soft"

    # Make sure the NFS mount point exists. If not, attempt to
    # create it. If the base portion of the mount location is
    # missing as well, signal an error and return.
    os.stat(self.nfsBaseDir)

    try:
      os.stat(self.nfsMountPoint)
    except OSError, e:
      if e.errno == 2:
        self.debug("Mount point %s was not found -- creating"
                   % self.nfsMountPoint)
        os.mkdir(self.nfsMountPoint)
    else:
      raise e

    rc = os.system("/bin/mount -t nfs -o %s %s %s" %
                   (mount_opts, self.mountSource,
                    self.nfsMountPoint))
    
    if rc != 0:
      self.debug("Mount of NFS failed.")
    else:
      self.debug("Mount of NFS succeeded.")

  def unmount(self):
    """Quick and dirty method to actually UNmount the real NFS connection
    somewhere else on the filesystem.
    """

    self.debug("Unmounting NFS mount from %s" %
               self.nfsMountPoint)
    rc = os.system("/bin/umount %s" % self.nfsMountPoint)

    if rc != 0:
      self.debug("Unmount of NFS failed.")
    else:
      self.debug("Unmount of NFS succeeded.")
