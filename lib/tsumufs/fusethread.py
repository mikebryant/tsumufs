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
    self.file_class    = tsumufs.FuseFile

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

    try:
      return os.lstat(tsumufs.nfsMountPoint + path)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def getxattr(self, path, name, size):
    self._debug("opcode: getxattr | path: %s | name: %s | size: %d"
                % (path, name, size))
    return -errno.ENOSYS

  def listxattr(self, path, size):
    self._debug("opcode: listxattr | path: %s | size: %d"
                % (path, size))
    return -errno.ENOSYS

  def readlink(self, path):
    self._debug("opcode: readlink | path: %s" % path)

    try:
      return os.readlink(tsumufs.nfsMountPoint + path)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def readdir(self, path, offset):
    self._debug("opcode: readdir | path: %s | offset: %d" % (path, offset))

    try:
      for file in os.listdir(tsumufs.nfsMountPoint + path):
        stat_result = os.lstat("%s%s/%s"
                               % (tsumufs.nfsMountPoint,
                                  path,
                                  file))

        dirent        = fuse.Direntry(file)
        dirent.type   = stat.S_IFMT(stat_result.st_mode)
        dirent.offset = offset
        
        yield dirent
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      yield e.errno

  def unlink(self, path):
    self._debug("opcode: unlink | path: %s" % path)

    try:
      return os.unlink(tsumufs.nfsMountPoint + path)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def rmdir(self, path):
    self._debug("opcode: rmdir | path: %s" % path)

    try:
      return os.rmdir(tsumufs.nfsMountPoint + path)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def symlink(self, src, dest):
    self._debug("opcode: symlink | src: %s | dest:: %s" % (src, dest))

    try:
      return os.symlink(src, tsumufs.nfsMountPoint + dest)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def rename(self, old, new):
    self._debug("opcode: rename | old: %s | new: %s" % (old, new))

    try:
      return os.rename(tsumufs.nfsMountPoint + old,
               tsumufs.nfsMountPoint + new)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def link(self, src, dest):
    self._debug("opcode: link | src: %s | dest: %s" % (src, dest))

    try:
      return os.link(tsumufs.nfsMountPoint + src,
                     tsumufs.nfsMountPoint + dest)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def chmod(self, path, mode):
    self._debug("opcode: chmod | path: %s | mode: %o" % (path, mode))

    try:
      return os.chmod(tsumufs.nfsMountPoint + path, mode)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno
    
  def chown(self, path, uid, gid):
    self._debug("opcode: chown | path: %s | uid: %d | gid: %d" %
               (path, uid, gid))

    try:
      return os.chown(tsumufs.nfsMountPoint + path, uid, gid)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def truncate(self, path, size=None):
    self._debug("opcode: truncate | path: %s | size: %d" %
               (path, size))

    try:
      fp = open(tsumufs.nfsMountPoint + path, "a")
      return fp.truncate(size)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def mknod(self, path, mode, dev):
    self._debug("opcode: mknod | path: %s | mode: %d | dev: %s" %
               (path, mode, dev))

    try:
      return os.mknod(tsumufs.nfsMountPoint + path, mode, dev)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def mkdir(self, path, mode):
    self._debug("opcode: mkdir | path: %s | mode: %o" % (path, mode))

    try:
      return os.mkdir(tsumufs.nfsMountPoint + path)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def utime(self, path, times):
    self._debug("opcode: utime | path: %s" % path)

    try:
      return os.utime(tsumufs.nfsMountPoint + path, times)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

  def access(self, path, mode):
    self._debug("opcode: access | path: %s | mode: %o" % (path, mode))

    try:
      if not os.access(tsumufs.nfsMountPoint + path, mode):
        return -errno.EACCES
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno

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
    
    try:
      if tsumufs.nfsAvailable.isSet():
        return os.statvfs(tsumufs.nfsMountPoint)
      else:
        return os.statvfs(tsumufs.cacheBaseDir)
    except OSError, e:
      self._debug("Caught OSError: errno %d: %s"
                  % (e.errno, e.strerror))
      return -e.errno
