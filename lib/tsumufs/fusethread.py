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

"""TsumuFS, a NFS-based caching filesystem."""

import os
import sys
import time

from fuse import Fuse
from errno import *
from stat import *
from threading import Thread, Semaphore, Event

from pprint import pprint

from triumvirate import *
from nfsmount import *
from synclog import *
from syncthread import *
from mountthread import *

class FuseThread(Triumvirate, Fuse):
  """Class that implements the prototype design of the TsumuFS
  filesystem. This class provides the main interface to Fuse. Note
  that this class is not a thread, yet it is considered as one in the
  design docs."""

  progName      = None
  mountOptions  = {}
  mountSource   = None
  mountPoint    = None
  nfsBaseDir    = "/var/lib/tsumufs/nfs"
  nfsMountPoint = None
  cacheBaseDir  = "/var/cache/tsumufs"
  cacheSpecDir  = "/var/lib/tsumufs/cachespec"
  cachePoint    = None

  tsumuMountedEvent = Event()
  nfsConnectedEvent = Event()
  
  syncThread    = None
  mountThread   = None

  def __init__(self, *args, **kw):
    """Initializer. Prepares the object for initial use. Parses command
    line arguments, and prepares a faked sys.argv for Fuse.__init__.

    Sadly, Fuse.__init__ requires the following format for it's
    command line arguments:

    ["<scriptname>", "<mountpoint>"]

    If we include the source in the argument list, it will erronously
    treat the source as the actual mount point. So we have to munge
    the list for it by directly modifying sys.argv.

    If there's a better way of doing this, I'm all ears. -- jtg"""

    # Parse our arguments
    self.debug("Parsing command line arguments.")
    self.parseArgs()
    
    # Command line argument munging and Fuse init
    self.debug("Initalizing fuse")
    sys.argv = [self.progName, self.mountPoint]
    Fuse.__init__(self, *args, **kw)

    # Setup the NFSMount object for both sync and mount threads to
    # handle.
    # TODO(jtgans): Is this needed anymore?
    #self.nfsMount = NFSMount(mountPoint, mountOptions)

    # Initialize our threads
    self.syncThread = SyncThread(self.tsumuMountedEvent,
                                 #self.nfsConnectedEvent,
                                 self.nfsMount)
    self.mountThread = MountThread(self.tsumuMountedEvent,
                                   #self.nfsConnectedEvent,
                                   self.nfsMount)

  def main(self):
    """Overrides Fuse.main(). Provides the case when the main event loop
    has exited, and we need to unmount the NFS mount and close the
    cache.

    Calls Fuse.main() first, and then does the unmount and cache
    closing operations after it returns."""

    self.debug("Entering fuse main event loop")
    Fuse.main(self)

    # Catch the case when the main event loop has exited. At this
    # point we want to unmount the NFS mount, and close the cache.
    self.debug("Unmounting NFS from %s" % self.nfsMountPoint)
    self._undoNFSMount()

  def parseArgs(self):
    """Parse the command line arguments into a usable set of
    variables. This sets the following instance variables:

        progName:
            The name of the program as reflected in sys.argv[0].

        mountOptions:
            The mount options passed verbatim from mount(8), in a
            comma separated list of key=value pairs, stored as a
            hash.

        mountSource:
            The NFS path to mount from.

        mountPoint:
            The local path to mount TsumuFS on.

    If the argument list is too short, or the -o option is missing
    arguments, this method will immediately exit the program with a
    code of 1."""

    self.progName = sys.argv[0]
    args = sys.argv[1:]
    opts_pos = 0

    # Find the mount options argument first
    for opts_pos in range(1, len(args)):
      if args[opts_pos] == "-o": break

    # Make sure that we have enough arguments to parse out the mount
    # options
    if len(args) == opts_pos:
      sys.stderr.write("%s: -o requires an option list.",
                       self.progName)
      sys.exit(1)
    else:
      # Burst the mount arguments separated by commas into a hash.
      opts = args[opts_pos+1].split(",")

      for opt in opts:
        key = opt.split("=")[0]

        # If the argument contains an equals, assume it's a string,
        # otherwise assume it's a boolean true value.
        if len(opt.split("=")) > 1:
          val = opt.split("=")[1]
        else:
          val = True

        self.mountOptions[key] = val

    # Now that we have burst the mount options, rip them out
    # of the argument list to prevent confusion with
    # positional arguments.
    args = args[0:opts_pos] + args[opts_pos+2:]

    # From here, assume the source and dest mount points are in
    # the positional arguments, and slice them out.
    if len(sys.argv) < 2:
      sys.stderr.write("%s: invalid number of arguments provided: " +
                       "expecting source and destination." %
                       self.progName)
      sys.exit(1)
    else:
      self.mountSource = args[0]
      self.mountPoint  = args[1]

    # Make sure the mountPoint is a fully qualified pathname.
      if self.mountPoint[0] != "/":
        self.mountPoint = os.getcwd() + "/" + self.mountPoint

    # Finally, calculate the runtime paths.
    self.nfsMountPoint = (self.nfsBaseDir + "/" +
                          self.mountPoint.replace("/", "-"))
    self.cachePoint = (self.cacheBaseDir + "/" +
                       self.mountPoint.replace("/", "-"))

  def debug(self, args):
    if debugMode:
      print("Main: " + args)

  ######################################################################
  # Filesystem operations and system calls below here

  def chown(self, path, uid, gid):
    self.debug("opcode: %s\n\tpath: %s\n\tuid: %d\n\tgid: %d\n" % ("chown", path, uid, gid))
    return os.chown(self.nfsMountPoint + path, uid, gid)

  def getattr(self, path):
    self.debug("opcode: %s\n\tpath: %s\n" % ("getattr", path))
    return os.stat(self.nfsMountPoint + path)

  def readlink(self, path):
    self.debug("opcode: %s\n\tpath: %s\n" % ("readlink", path))
    return os.readlink(self.nfsMountPoint + path)

  def getdir(self, path):
    self.debug("opcode: %s\n\tpath: %s\n" % ("getdir", path))

    dentries = []
    files = os.listdir(self.nfsMountPoint + path)

    for f in files:
      dentries.append((f, 0))

      return dentries

  def unlink(self, path):
    self.debug("opcode: %s\n\tpath: %s\n" % ("unlink", path))
    return os.unlink(self.nfsMountPoint + path)

  def rmdir(self, path):
    self.debug("opcode: %s\n\tpath: %s\n" % ("rmdir", path))
    return os.rmdir(self.nfsMountPoint + path)

  def symlink(self, src, dest):
    self.debug("opcode: %s\n\tsrc: %s\n\tdest:: %s\n" % ("symlink", src, dest))
    return -ENOSYS

  def rename(self, old, new):
    self.debug("opcode: %s\n\told: %s\n\tnew: %s\n" % ("rename", old, new))
    return -ENOSYS

  def link(self, src, dest):
    self.debug("opcode: %s\n\tsrc: %s\n\tdest: %s\n" % ("link", src, dest))
    return -ENOSYS

  def chmod(self, path, mode):
    self.debug("opcode: %s\n\tpath: %s\n\tmode: %o\n" % ("chmod", path, mode))
    return -ENOSYS

  def truncate(self, path, size):
    self.debug("opcode: %s\n\tpath: %s\n\tsize: %d\n" % ("truncate", path, size))
    return -ENOSYS

  def mknod(self, path, mode, dev):
    self.debug("opcode: %s\n\tpath: %s\n\tmode: %d\n\tdev: %s\n" % ("mknod", path, mode, dev))
    return -ENOSYS

  def mkdir(self, path, mode):
    self.debug("opcode: %s\n\tpath: %s\n\tmode: %o\n" % ("mkdir", path, mode))
    return os.mkdir(self.nfsMountPoint + path)

  def utime(self, path, times):
    self.debug("opcode: %s\n\tpath: %s\n" % ("utime", path))
    return -ENOSYS

  def open(self, path, flags):
    self.debug("opcode: %s\n\tpath: %s\n" % ("open", path))
    return -ENOSYS

  def read(self, path, length, offset):
    self.debug("opcode: %s\n\tpath: %s\n\tlen: %d\n\toffset: %d\n" % ("read", path, length, offset))
    return -ENOSYS

  def write(self, path, buf, offset):
    self.debug("opcode: %s\n\tpath: %s\n\tbuf: '%s'\n\toffset: %d\n" % ("write", path, buf, offset))
    return -ENOSYS

  def release(self, path, flags):
    self.debug("opcode: %s\n\tpath: %s\n\tflags: %s" % ("release", path, flags))
    return -ENOSYS

  def statfs(self):
    self.debug("opcode: %s\n" % "statfs")
    return -ENOSYS

  def fsync(self, path, isfsyncfile):
    self.debug("opcode: %s\n\tpath: %s\n" % ("fsync", path))
    return -ENOSYS

# static struct fuse_operations xmp_oper = {
#     .getattr	= xmp_getattr,
#     .readlink	= xmp_readlink,
#     .getdir	= xmp_getdir,
#     .mknod	= xmp_mknod,
#     .mkdir	= xmp_mkdir,
#     .symlink	= xmp_symlink,
#     .unlink	= xmp_unlink,
#     .rmdir	= xmp_rmdir,
#     .rename	= xmp_rename,
#     .link	= xmp_link,
#     .chmod	= xmp_chmod,
#     .chown	= xmp_chown,
#     .truncate	= xmp_truncate,
#     .utime	= xmp_utime,
#     .open	= xmp_open,
#     .read	= xmp_read,
#     .write	= xmp_write,
#     .statfs	= xmp_statfs,
#     .release	= xmp_release,
#     .fsync	= xmp_fsync
# };
