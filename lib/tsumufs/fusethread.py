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

import os
import sys
import errno
import stat
import statvfs
import time
import threading

import fuse
from fuse import Fuse

import tsumufs

class FuseThread(tsumufs.Triumvirate, Fuse):
  """Class that implements the prototype design of the TsumuFS
  filesystem. This class provides the main interface to Fuse. Note
  that this class is not a thread, yet it is considered as one in the
  design docs."""

  syncThread    = None
  mountThread   = None

  def __init__(self, *args, **kw):
    """Initializer. Prepares the object for initial use."""

    Fuse.__init__(self, *args, **kw)
    self._setName("fuse")
    self.multithreaded = 1
    
  def fsinit(self):
    # Set the initial states for the events.
    self._debug("Setting initial states for events.")
    tsumufs.unmountedEvent.clear()
    tsumufs.nfsConnectedEvent.clear()

    # Setup the NFSMount object for both sync and mount threads to
    # access raw NFS with.
    self._debug("Initializing nfsMount proxy.")
    tsumufs.nfsMount = tsumufs.NFSMount()

    # Initialize our threads
    self._debug("Initializing threads.")
    #self._syncThread = SyncThread()
    self._mountThread = tsumufs.MountThread()

    # Start the threads
    self._debug("Starting threads.")
    self._mountThread.start()

    self._debug('fsinit complete.')
    
  def main(self, *args, **kw):
    Fuse.main(self, *args, **kw)
    self._debug("Fuse main event loop exited.")

    self._debug("Clearing mountedEvent.")
    tsumufs.unmountedEvent.set()
    tsumufs.unmountedEvent.notify()

    self._debug("Waiting for the mount thread to finish.")
    self._mountThread.join()

    self._debug("Shutdown complete.")

  def parseCommandLine(self):
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

    # Setup our option parser to not be retarded.
    self.parser = fuse.FuseOptParse(standard_mods=False,
                                    fetch_mp=False,
                                    dash_s_do='undef')

    # Add in the named options we care about.
    self.parser.add_option(mountopt='nfsbasedir',
                           default='/var/lib/tsumufs/nfs',
                           help=('Set the NFS mount base directory [default: ' 
                                 '%default]'))
    self.parser.add_option(mountopt='nfsmountopts',
                           default=None,
                           help=('A comma-separated list of key-value '
                                 'pairs that adjust how the NFS mount '
                                 'point is mounted. [default: '
                                 '%default]'))
    self.parser.add_option(mountopt='nfsmountpoint',
                           default=None,
                           help=('Set the directory name of the nfs mount '
                                 'point [default: calculated based upon the '
                                 'source]'))
    self.parser.add_option(mountopt='cachebasedir',
                           default='/var/cache/tsumufs',
                           help=('Set the base directory for cache storage '
                                 '[default: %default]'))
    self.parser.add_option(mountopt='cachespecdir',
                           default='/var/lib/tsumufs/cachespec',
                           help=('Set the base directory for cachespec '
                                 'storage [default: %default]'))
    self.parser.add_option(mountopt='cachepoint',
                           default=None,
                           help=('Set the directory name for cache storage '
                                 '[default: calculated]'))
    
    self.parser.add_option('-f',
                           action='callback',
                           callback=lambda *a:
                             self.fuse_args.setmod('foreground'),
                           help=('Prevents TsumuFS from forking into '
                                 'the background.'))
    self.parser.add_option('-D', '--fuse-debug',
                           action='callback',
                           callback=lambda *a:
                             self.fuse_args.add('debug'),
                           help=('Turns on fuse-python debugging. '
                                 'Only useful if you also specify '
                                 '-f. Typically only useful to '
                                 'developers.'))
    self.parser.add_option('-d', '--debug',
                           dest='debugMode',
                           action='store_true',
                           default=False,
                           help='Enable debug messages. [default: %default]')

    # GO!
    self.parse(values=tsumufs, errex=1)

    # Verify we have a source and destination to mount.
    if len(self.cmdline[1]) != 2:
      sys.stderr.write(("%s: invalid number of arguments provided: "
                       "expecting source and destination.\n") %
                       tsumufs.progName)
      sys.exit(1)

    # Pull out the source and point
    tsumufs.mountSource = self.cmdline[1][0]
    tsumufs.mountPoint  = self.cmdline[1][1]

    # Make sure the mountPoint is a fully qualified pathname.
    if tsumufs.mountPoint[0] != "/":
      tsumufs.mountPoint = os.getcwd() + "/" + tsumufs.mountPoint

    # Shove the proper mountPoint into FUSE's mouth.
    self.fuse_args.mountpoint = tsumufs.mountPoint

    # Finally, calculate the runtime paths.
    tsumufs.nfsMountPoint = (tsumufs.nfsBaseDir + "/" +
                             tsumufs.mountPoint.replace("/", "-"))
    tsumufs.cachePoint = (tsumufs.cacheBaseDir + "/" +
                          tsumufs.mountPoint.replace("/", "-"))

    self._debug("mountPoint is %s" % tsumufs.mountPoint)
    self._debug("nfsMountPoint is %s" % tsumufs.nfsMountPoint)
    self._debug("cachePoint is %s" % tsumufs.cachePoint)


  ######################################################################
  # Filesystem operations and system calls below here

  def getattr(self, path):
    self._debug("getattr: %s" % tsumufs.nfsMountPoint + path)
    return os.lstat(tsumufs.nfsMountPoint + path)

  def readlink(self, path):
    self._debug("opcode: %s\n\tpath: %s\n" % ("readlink", path))
    return os.readlink(tsumufs.nfsMountPoint + path)

  def readdir(self, path, offset):
    self._debug("readdir: %s (%d)" % (path, offset))

    for file in os.listdir(tsumufs.nfsMountPoint + path):
      dirent        = fuse.Direntry(file)
      dirent.type   = stat.S_IFMT(os.stat(file))
      dirent.offset = offset

      yield dirent

  def readlink(self, path):
    self._debug("readlink: %s" % path)
    return os.readlink(tsumufs.nfsMountPoint + path)


  def unlink(self, path):
    self._debug("opcode: %s\n\tpath: %s\n" % ("unlink", path))
    return os.unlink(tsumufs.nfsMountPoint + path)

  def rmdir(self, path):
    self._debug("opcode: %s\n\tpath: %s\n" % ("rmdir", path))
    return os.rmdir(tsumufs.nfsMountPoint + path)

  def symlink(self, src, dest):
    self._debug("opcode: %s\n\tsrc: %s\n\tdest:: %s\n" % ("symlink", src, dest))
    return -ENOSYS

  def rename(self, old, new):
    self._debug("opcode: %s\n\told: %s\n\tnew: %s\n" % ("rename", old, new))
    return -ENOSYS

  def link(self, src, dest):
    self._debug("opcode: %s\n\tsrc: %s\n\tdest: %s\n" % ("link", src, dest))
    return -ENOSYS

  def chmod(self, path, mode):
    self._debug("opcode: %s\n\tpath: %s\n\tmode: %o\n" % ("chmod", path, mode))
    return -ENOSYS

  def chown(self, path, uid, gid):
    self._debug("opcode: %s\n\tpath: %s\n\tuid: %d\n\tgid: %d\n" %
               ("chown", path, uid, gid))
    return os.chown(tsumufs.nfsMountPoint + path, uid, gid)

  def truncate(self, path, size):
    self._debug("opcode: %s\n\tpath: %s\n\tsize: %d\n" %
               ("truncate", path, size))
    return -ENOSYS

  def mknod(self, path, mode, dev):
    self._debug("opcode: %s\n\tpath: %s\n\tmode: %d\n\tdev: %s\n" %
               ("mknod", path, mode, dev))
    return -ENOSYS

  def mkdir(self, path, mode):
    self._debug("opcode: %s\n\tpath: %s\n\tmode: %o\n" % ("mkdir", path, mode))
    return os.mkdir(tsumufs.nfsMountPoint + path)

  def utime(self, path, times):
    self._debug("opcode: %s\n\tpath: %s\n" % ("utime", path))
    return -ENOSYS

#    The following utimens method would do the same as the above utime method.
#    We can't make it better though as the Python stdlib doesn't know of
#    subsecond preciseness in acces/modify times.
#  
#    def utimens(self, path, ts_acc, ts_mod):
#      os.utime("." + path, (ts_acc.tv_sec, ts_mod.tv_sec))

  def access(self, path, mode):
    if not os.access("." + path, mode):
      return -EACCES

#    This is how we could add stub extended attribute handlers...
#    (We can't have ones which aptly delegate requests to the underlying fs
#    because Python lacks a standard xattr interface.)
#
#    def getxattr(self, path, name, size):
#        val = name.swapcase() + '@' + path
#        if size == 0:
#            # We are asked for size of the value.
#            return len(val)
#        return val
#
#    def listxattr(self, path, size):
#        # We use the "user" namespace to please XFS utils
#        aa = ["user." + a for a in ("foo", "bar")]
#        if size == 0:
#            # We are asked for size of the attr list, ie. joint size of attrs
#            # plus null separators.
#            return len("".join(aa)) + len(aa)
#        return aa

  def statfs(self):
    """
    Should return an object with statvfs attributes (f_bsize, f_frsize...).
    Eg., the return value of os.statvfs() is such a thing (since py 2.2).
    If you are not reusing an existing statvfs object, start with
    fuse.StatVFS(), and define the attributes.
    
    To provide usable information (ie., you want sensible df(1)
    output, you are suggested to specify the following attributes:
    
    - f_bsize - preferred size of file blocks, in bytes
    - f_frsize - fundamental size of file blcoks, in bytes
    [if you have no idea, use the same as blocksize]
    - f_blocks - total number of blocks in the filesystem
    - f_bfree - number of free blocks
    - f_files - total number of file inodes
    - f_ffree - nunber of free file inodes
    """
    
    return os.statvfs(tsumufs.nfsMountPoint)
  
  def open(self, path, flags):
    self._debug("opcode: %s\n\tpath: %s\n" % ("open", path))
    return -ENOSYS

  def read(self, path, length, offset):
    self._debug("opcode: %s\n\tpath: %s\n\tlen: %d\n\toffset: %d\n" %
               ("read", path, length, offset))
    return -ENOSYS

  def write(self, path, buf, offset):
    self._debug("opcode: %s\n\tpath: %s\n\tbuf: '%s'\n\toffset: %d\n" %
               ("write", path, buf, offset))
    return -ENOSYS

  def release(self, path, flags):
    self._debug("opcode: %s\n\tpath: %s\n\tflags: %s" % ("release", path, flags))
    return -ENOSYS

  def statfs(self):
    """
    Should return a tuple with the following 6 elements:
      - blocksize - size of file blocks, in bytes
      - totalblocks - total number of blocks in the filesystem
      - freeblocks - number of free blocks
      - totalfiles - total number of file inodes
      - freefiles - nunber of free file inodes
      - namelen - the maximum length of filenames
    Feel free to set any of the above values to 0, which tells
    the kernel that the info is not available.
    """

    self._debug("opcode: %s\n" % "statfs")

    result = os.statvfs(tsumufs.nfsMountPoint)

    return (result[statvfs.F_FRSIZE],   # Block size
            result[statvfs.F_BLOCKS],   # Total blocks
            result[statvfs.F_BFREE],    # blocks_free
            result[statvfs.F_FILES],    # files
            result[statvfs.F_FFREE],    # files_free
            result[statvfs.F_NAMEMAX])  # Max filename length

  def fsync(self, path, isfsyncfile):
    self._debug("opcode: %s\n\tpath: %s\n" % ("fsync", path))
    return -ENOSYS

# # static struct fuse_operations xmp_oper = {
# #     .getattr	= xmp_getattr,
# #     .readlink	= xmp_readlink,
# #     .getdir	= xmp_getdir,
# #     .mknod	= xmp_mknod,
# #     .mkdir	= xmp_mkdir,
# #     .symlink	= xmp_symlink,
# #     .unlink	= xmp_unlink,
# #     .rmdir	= xmp_rmdir,
# #     .rename	= xmp_rename,
# #     .link	= xmp_link,
# #     .chmod	= xmp_chmod,
# #     .chown	= xmp_chown,
# #     .truncate	= xmp_truncate,
# #     .utime	= xmp_utime,
# #     .open	= xmp_open,
# #     .read	= xmp_read,
# #     .write	= xmp_write,
# #     .statfs	= xmp_statfs,
# #     .release	= xmp_release,
# #     .fsync	= xmp_fsync
# # };
