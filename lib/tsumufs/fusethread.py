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
import traceback

import fuse
from fuse import Fuse

import tsumufs

class FuseThread(tsumufs.Triumvirate, Fuse):
  """Class that implements the prototype design of the TsumuFS
  filesystem. This class provides the main interface to Fuse. Note
  that this class is not a thread, yet it is considered as one in the
  design docs."""

  syncThread    = None

  def __init__(self, *args, **kw):
    """Initializer. Prepares the object for initial use."""

    Fuse.__init__(self, *args, **kw)
    self._setName("fuse")
    self.multithreaded = 1
    
  def fsinit(self):
    # Setup the NFSMount object for both sync and mount threads to
    # access raw NFS with.
    self._debug("Initializing nfsMount proxy.")
    tsumufs.nfsMount = tsumufs.NFSMount()

    # Initialize our threads
    self._debug("Initializing sync thread.")

    try:
      self._syncThread = tsumufs.SyncThread()
    except:
      self._debug("Exception: %s" % traceback.format_exc())
      return False

    # Start the threads
    self._debug("Starting sync thread.")
    self._syncThread.start()

    self._debug('fsinit complete.')
    
  def main(self, *args, **kw):
    Fuse.main(self, *args, **kw)
    self._debug("Fuse main event loop exited.")

    self._debug("Setting event and condition states.")
    tsumufs.unmounted.set()
    tsumufs.nfsAvailable.clear()

    self._debug("Waiting for the sync thread to finish.")
    self._syncThread.join()

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
    
    self.parser.add_option('-O',
                           dest='mountOptions',
                           default=None,
                           help=('A comma-separated list of key-value '
                                 'pairs that adjust how the NFS mount '
                                 'point is mounted. [default: '
                                 '%default]'))

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
    self._debug("mountOptions is %s" % tsumufs.mountOptions)


  ######################################################################
  # Filesystem operations and system calls below here

  def getattr(self, path):
    self._debug("opcode: getattr | path: %s" % path)
    return os.lstat(tsumufs.nfsMountPoint + path)

  def readlink(self, path):
    self._debug("opcode: readlink | path: %s" % path)
    return os.readlink(tsumufs.nfsMountPoint + path)

  def readdir(self, path, offset):
    self._debug("opcode: readdir | path: %s | offset: %d" % (path, offset))

    try:
      for file in os.listdir(tsumufs.nfsMountPoint + path):
        stat_result = os.lstat("%s%s%s"
                               % (tsumufs.nfsMountPoint,
                                  path,
                                  file))

        dirent        = fuse.Direntry(file)
        dirent.type   = stat.S_IFMT(stat_result.st_mode)
        dirent.offset = offset
        
        yield dirent
    except:
      self._debug("readdir: Unable to read dir %s: %s" %
                  (tsumufs.nfsMountPoint + path,
                   traceback.format_exc()))
      yield -ENOSYS

  def unlink(self, path):
    self._debug("opcode: unlink | path: %s" % path)
    return os.unlink(tsumufs.nfsMountPoint + path)

  def rmdir(self, path):
    self._debug("opcode: rmdir | path: %s" % path)
    return os.rmdir(tsumufs.nfsMountPoint + path)

  def symlink(self, src, dest):
    self._debug("opcode: symlink | src: %s | dest:: %s" % (src, dest))
    return os.symlink(src, tsumufs.nfsMountPoint + dest)

  def rename(self, old, new):
    self._debug("opcode: rename | old: %s | new: %s" % (old, new))
    return os.rename(tsumufs.nfsMountPoint + old,
                     tsumufs.nfsMountPoint + new)

  def link(self, src, dest):
    self._debug("opcode: link | src: %s | dest: %s" % (src, dest))
    return os.link(tsumufs.nfsMountPoint + src,
                   tsumufs.nfsMountPoint + dest)

  def chmod(self, path, mode):
    self._debug("opcode: chmod | path: %s | mode: %o" % (path, mode))
    return os.chmod(tsumufs.nfsMountPoint + path, mode)

  def chown(self, path, uid, gid):
    self._debug("opcode: chown | path: %s | uid: %d | gid: %d" %
               (path, uid, gid))
    return os.chown(tsumufs.nfsMountPoint + path, uid, gid)

  def truncate(self, path, size):
    self._debug("opcode: truncate | path: %s | size: %d" %
               (path, size))
    return -ENOSYS

  def mknod(self, path, mode, dev):
    self._debug("opcode: mknod | path: %s | mode: %d | dev: %s" %
               (path, mode, dev))
    return os.mknod(tsumufs.nfsMountPoint + path, mode, dev)

  def mkdir(self, path, mode):
    self._debug("opcode: mkdir | path: %s | mode: %o" % (path, mode))
    return os.mkdir(tsumufs.nfsMountPoint + path)

  def utime(self, path, times):
    self._debug("opcode: utime | path: %s" % path)
    return os.utime(tsumufs.nfsMountPoint + path, times)

#    The following utimens method would do the same as the above utime method.
#    We can't make it better though as the Python stdlib doesn't know of
#    subsecond preciseness in acces/modify times.
#  
#    def utimens(self, path, ts_acc, ts_mod):
#      os.utime("." + path, (ts_acc.tv_sec, ts_mod.tv_sec))

  def access(self, path, mode):
    self._debug("opcode: access | path: %s | mode: %o" % (path, mode))
    if not os.access(tsumufs.nfsMountPoint + path, mode):
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
    self._debug("opcode: statfs")
    
    return os.statvfs(tsumufs.nfsMountPoint)
  
  def open(self, path, flags):
    self._debug("opcode: open | path: %s" % path)
    return -ENOSYS

  def read(self, path, length, offset):
    self._debug("opcode: open | path: %s | len: %d | offset: %d" %
               (path, length, offset))
    return -ENOSYS

  def write(self, path, buf, offset):
    self._debug("opcode: write | path: %s | buf: '%s' | offset: %d" %
               (path, buf, offset))
    return -ENOSYS

  def release(self, path, flags):
    self._debug("opcode: release | path: %s | flags: %s" % (path, flags))
    return -ENOSYS

  def fsync(self, path, isfsyncfile):
    self._debug("opcode: fsync | path: %s | isfsyncfile: %d"
                % (path, isfsyncfile))
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
