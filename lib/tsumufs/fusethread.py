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
import os.path
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
  '''
  Class that implements the prototype design of the TsumuFS
  filesystem. This class provides the main interface to Fuse. Note
  that this class is not a thread, yet it is considered as one in the
  design docs.
  '''

  syncThread    = None

  def __init__(self, *args, **kw):
    '''
    Initializer. Prepares the object for initial use.
    '''

    Fuse.__init__(self, *args, **kw)

    self.multithreaded = 1
    self.file_class    = tsumufs.FuseFile

  def fsinit(self):
    '''
    Method callback that is called when FUSE's initial startup has
    completed, and the initialization of our client filesystem should
    start.

    Basic setup is done in here, such as instanciation of new objects
    and the startup of threads.
    '''

    self._debug('Initializing cachemanager object.')
    try:
      tsumufs.cacheManager = tsumufs.CacheManager()
    except:
      self._debug('Exception: %s' % traceback.format_exc())
      return False

    # Setup the NFSMount object for both sync and mount threads to
    # access raw NFS with.
    self._debug('Initializing nfsMount proxy.')
    try:
      tsumufs.nfsMount = tsumufs.NFSMount()
    except:
      # TODO(jtg): Erm... WHY can't we call tsumufs.syslogExceptHook here? O.o
      exc_info = sys.exc_info()

      self._debug('*** Unhandled exception occurred')
      self._debug('***     Type: %s' % str(exc_info[0]))
      self._debug('***    Value: %s' % str(exc_info[1]))
      self._debug('*** Traceback:')

      for line in traceback.extract_tb(exc_info[2]):
        self._debug('***    %s(%d) in %s: %s' % line)

      return False

    # Initialize our threads
    self._debug('Initializing sync thread.')
    try:
      self._syncThread = tsumufs.SyncThread()
    except:
      # TODO(jtg): Same as above... We should really fix this.
      exc_info = sys.exc_info()

      self._debug('*** Unhandled exception occurred')
      self._debug('***     Type: %s' % str(exc_info[0]))
      self._debug('***    Value: %s' % str(exc_info[1]))
      self._debug('*** Traceback:')

      for line in traceback.extract_tb(exc_info[2]):
        self._debug('***    %s(%d) in %s: %s' % line)

      return False

    # Start the threads
    self._debug('Starting sync thread.')
    self._syncThread.start()

    self._debug('fsinit complete.')

  def main(self, args=None):
    '''
    Mainline of the FUSE client filesystem. This directly overrides
    the Fuse.main() method to allow us to manually shutdown things
    after the FUSE event loop has finished.
    '''

    Fuse.main(self, args)
    self._debug('Fuse main event loop exited.')

    self._debug('Setting event and condition states.')
    tsumufs.unmounted.set()
    tsumufs.nfsAvailable.clear()

    self._debug('Waiting for the sync thread to finish.')
    self._syncThread.join()

    self._debug('Shutdown complete.')

  def parseCommandLine(self):
    '''
    Parse the command line arguments into a usable set of
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
    code of 1.
    '''

    # Setup our option parser to not be retarded.
    self.parser = fuse.FuseOptParse(standard_mods=False,
                                    fetch_mp=False,
                                    dash_s_do='undef')

    # Add in the named options we care about.
    self.parser.add_option(mountopt='nfsbasedir',
                           dest='nfsBaseDir',
                           default='/var/lib/tsumufs/nfs',
                           help=('Set the NFS mount base directory [default: '
                                 '%default]'))
    self.parser.add_option(mountopt='nfsmountpoint',
                           dest='nfsMountPoint',
                           default=None,
                           help=('Set the directory name of the nfs mount '
                                 'point [default: calculated based upon the '
                                 'source]'))
    self.parser.add_option(mountopt='cachebasedir',
                           dest='cacheBaseDir',
                           default='/var/cache/tsumufs',
                           help=('Set the base directory for cache storage '
                                 '[default: %default]'))
    self.parser.add_option(mountopt='cachespecdir',
                           dest='cacheSpecDir',
                           default='/var/lib/tsumufs/cachespec',
                           help=('Set the base directory for cachespec '
                                 'storage [default: %default]'))
    self.parser.add_option(mountopt='cachepoint',
                           dest='cachePoint',
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
                           callback=lambda:
                             self.fuse_args.setmod('foreground'),
                           help=('Prevents TsumuFS from forking into '
                                 'the background.'))
    self.parser.add_option('-D', '--fuse-debug',
                           action='callback',
                           callback=lambda:
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
      sys.stderr.write(('%s: invalid number of arguments provided: '
                       'expecting source and destination.\n') %
                       tsumufs.progName)
      sys.exit(1)

    # Pull out the source and point
    tsumufs.mountSource = self.cmdline[1][0]
    tsumufs.mountPoint  = self.cmdline[1][1]

    # Make sure the source and point don't contain trailing slashes.
    if tsumufs.mountSource[-1] == '/':
      tsumufs.mountSource = tsumufs.mountSource[:-1]
    if tsumufs.mountPoint[-1] == '/':
      tsumufs.mountPoint = tsumufs.mountPoint[:-1]

    # Make sure the mountPoint is a fully qualified pathname.
    if tsumufs.mountPoint[0] != '/':
      tsumufs.mountPoint = os.getcwd() + '/' + tsumufs.mountPoint

    # Shove the proper mountPoint into FUSE's mouth.
    self.fuse_args.mountpoint = tsumufs.mountPoint

    self._debug('nfsMountPoint is %s' % tsumufs.nfsMountPoint)
    self._debug('cachePoint is %s' % tsumufs.cachePoint)

    # Finally, calculate the runtime paths if they weren't specified already.
    if tsumufs.nfsMountPoint == None:
      tsumufs.nfsMountPoint = (tsumufs.nfsBaseDir + '/' +
                               tsumufs.mountPoint.replace('/', '-'))

    if tsumufs.cachePoint == None:
      tsumufs.cachePoint = (tsumufs.cacheBaseDir + '/' +
                            tsumufs.mountPoint.replace('/', '-'))

    self._debug('mountPoint is %s' % tsumufs.mountPoint)
    self._debug('nfsMountPoint is %s' % tsumufs.nfsMountPoint)
    self._debug('cachePoint is %s' % tsumufs.cachePoint)
    self._debug('mountOptions is %s' % tsumufs.mountOptions)


  ######################################################################
  # Filesystem operations and system calls below here

  def getattr(self, path):
    '''
    Callback which is called into when a stat() is performed on the
    user side of things.

    Returns:
      A stat result object, the same as an os.lstat() call.

    Raises:
      None
    '''

    self._debug('opcode: getattr | path: %s' % path)

    try:
      return tsumufs.cacheManager.statFile(path)
    except OSError, e:
      self._debug('getattr: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def setxattr(self, path, name, value, size):
    '''
    Callback that is called into when a setxattr() call is
    performed. This sets the value of an extended attribute, if that
    attribute is non-readonly. If the attribute isn't a valid name, or
    is read-only, this method returns -errno.EOPNOTSUPP.

    Returns:
      None, or -EOPNOTSUPP on error.
    '''

    self._debug(('opcode: setxattr | path: %s | name: %s | '
                 'value: %s | size: %d')
                % (path, name, value, size))

    # TODO: make this get the real xattrs from the file, and allow for setting
    # other xattrs that aren't ones we control.

    # TODO: make setting read-only tsumufs xattrs return -EOPNOTSUPP.

    # TODO: make this actually change the cached state of the file in question.

    if name == 'tsumufs.in-cache':
      if value == '0':
        return
      elif value == '1':
        return

    if path == '/':
      if name == 'tsumufs.force-disconnect':
        if value == '0':
          tsumufs.forceDisconnect.clear()
          return
        elif value == '1':
          tsumufs.forceDisconnect.set()
          tsumufs.nfsMount.unmount()
          tsumufs.nfsAvailable.clear()
          return

    return -errno.EOPNOTSUPP

  def getxattr(self, path, name, size):
    '''
    Callback that is called to get a specific extended attribute size
    or value by name.

    Returns:
      The size of the value (including the null terminator) if size is
        set to 0.
      The string the extended attribute contains if size > 0
      -EOPNOTSUPP if the name is invalid.
    '''

    self._debug('opcode: getxattr | path: %s | name: %s | size: %d'
                % (path, name, size))

    # TODO: make this get the real xattrs from the file, and combine with our
    # own.

    if size == 0:
      # Caller just wants the size of the value. All of our values are either 1
      # or 0 followed by a null, so we return a hardcoded value of 2 here.
      return 2

    xattrs = {
      'tsumufs.in-cache': '0',
      'tsumufs.dirty': '0'
      }

    if tsumufs.cacheManager.isCachedToDisk(path):
      xattrs['tsumufs.in-cache'] = '1'

    if tsumufs.cacheManager.cachedFileIsDirty(path):
      xattrs['tsumufs.dirty'] = '1'

    if path == '/':
      xattrs['tsumufs.version'] = '.'.join(map(str, tsumufs.__version__))
      xattrs['tsumufs.force-disconnect'] = (tsumufs.forceDisconnect.isSet() and
                                    '1' or '0')
      xattrs['tsumufs.connected'] = tsumufs.nfsAvailable.isSet() and '1' or '0'

    name = name.lower()

    try:
      return xattrs[name]
    except KeyError:
      return -errno.EOPNOTSUPP

  def listxattr(self, path, size):
    '''
    Callback method to list the names of valid extended attributes in
    a file.

    Returns:
      The number of variables available if size is 0.
      A list of key names if size > 0.
    '''

    self._debug('opcode: listxattr | path: %s | size: %d'
                % (path, size))

    # TODO: make this get the real xattrs from the file, and combine with our
    # own.

    keys = ['tsumufs.in-cache', 'tsumufs.dirty']

    if path == '/':
      keys.append('tsumufs.force-disconnect')
      keys.append('tsumufs.connected')
      keys.append('tsumufs.version')

    if size == 0:
      return len(''.join(keys)) + len(keys)

    return keys

  def readlink(self, path):
    '''
    Reads the value of a symlink.

    Returns:
      The string representation of the file the symlink points to, or
      a negative errno code on error.
    '''

    self._debug('opcode: readlink | path: %s' % path)

    try:
      retval = tsumufs.cacheManager.readLink(path)
      self._debug('returning: %s' % retval)
      return retval
    except OSError, e:
      self._debug('readlink: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def readdir(self, path, offset):
    '''
    Generator callback that returns a fuse.Direntry object every time
    it is called. Similar to the C readdir() call.

    Returns:
      A generator that yields a fuse.Direntry object, or an errno
      code on error.
    '''

    self._debug('opcode: readdir | path: %s | offset: %d' % (path, offset))

    try:
      for filename in tsumufs.cacheManager.getDirents(path):
        pathname = os.path.join(path, filename)
        stat_result = tsumufs.cacheManager.statFile(pathname)

        dirent        = fuse.Direntry(filename)
        dirent.type   = stat.S_IFMT(stat_result.st_mode)
        dirent.offset = offset

        yield dirent
    except OSError, e:
      self._debug('readdir: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      yield -e.errno

  def unlink(self, path):
    '''
    Callback to unlink a file on disk.

    Returns:
      True on successful unlink, or an errno code on error.
    '''

    self._debug('opcode: unlink | path: %s' % path)

    try:
      os.unlink(tsumufs.nfsMountPoint + path)
      tsumufs.cacheManager.removeCachedFile(path)

      return True
    except OSError, e:
      self._debug('unlink: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def rmdir(self, path):
    '''
    Removes a directory from disk.

    Returns:
      True on successful unlink, or errno code on error.
    '''

    self._debug('opcode: rmdir | path: %s' % path)

    try:
      os.rmdir(tsumufs.nfsMountPoint + path)
      tsumufs.cacheManager.removeCachedFile(path)

      return True
    except OSError, e:
      self._debug('rmdir: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def symlink(self, src, dest):
    '''
    Creates a symlink pointing to src as a file called dest.

    Returns:
      True on successful link creation, or errno code on error.
    '''

    self._debug('opcode: symlink | src: %s | dest:: %s' % (src, dest))

    try:
      os.symlink(src, tsumufs.nfsMountPoint + dest)
      return True
    except OSError, e:
      self._debug('symlink: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def rename(self, old, new):
    '''
    Renames a file from old to new, possibly changing it's path as
    well as its filename.

    Returns:
      True on successful rename, or errno code on error.
    '''

    self._debug('opcode: rename | old: %s | new: %s' % (old, new))

    try:
      return os.rename(tsumufs.nfsMountPoint + old,
               tsumufs.nfsMountPoint + new)
    except OSError, e:
      self._debug('rename: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def link(self, src, dest):
    '''
    Links a the dest filename to the inode number of the src
    filename.

    Returns:
      True on successful linking, or errno code on error.
    '''

    self._debug('opcode: link | src: %s | dest: %s' % (src, dest))

    try:
      return os.link(tsumufs.nfsMountPoint + src,
                     tsumufs.nfsMountPoint + dest)
    except OSError, e:
      self._debug('link: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def chmod(self, path, mode):
    '''
    Changes the mode of a file.

    Returns:
      True on successful mode change, or errno code on error.
    '''

    self._debug('opcode: chmod | path: %s | mode: %o' % (path, mode))

    try:
      # TODO(jtg): Make this actually chmod the files on NFS.
      return 0
    except OSError, e:
      self._debug('chmod: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def chown(self, path, uid, gid):
    '''
    Change the owner and/or group of a file.

    Returns:
      True on successful change, otherwise errno code is returned.
    '''

    self._debug('opcode: chown | path: %s | uid: %d | gid: %d' %
               (path, uid, gid))

    try:
      return os.chown(tsumufs.nfsMountPoint + path, uid, gid)
    except OSError, e:
      self._debug('chown: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def truncate(self, path, size=None):
    '''
    Truncate a file to zero length.

    Returns:
      0 on successful truncation, otherwise an errno code is
      returned.
    '''

    self._debug('opcode: truncate | path: %s | size: %d' %
               (path, size))

    try:
      fp = open(tsumufs.nfsMountPoint + path, 'a')
      fp.truncate(size)

      return 0
    except OSError, e:
      self._debug('truncate: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def mknod(self, path, mode, dev):
    '''
    Creates a special device file with the sepcified mode and device
    number.

    Returns:
      True on successful creation, otherwise an errno code is
      returned.
    '''

    self._debug('opcode: mknod | path: %s | mode: %d | dev: %s' %
               (path, mode, dev))

    try:
      return os.mknod(tsumufs.nfsMountPoint + path, mode, dev)
    except OSError, e:
      self._debug('mknod: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def mkdir(self, path, mode):
    '''
    Creates a new directory with the specified mode.

    Returns:
      True on successful creation, othwerise an errno code is
      returned.
    '''

    self._debug('opcode: mkdir | path: %s | mode: %o' % (path, mode))

    try:
      return os.mkdir(tsumufs.nfsMountPoint + path)
    except OSError, e:
      self._debug('mkdir: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def utime(self, path, times):
    '''
    Set the times (atime, mtime, and ctime) of a file.

    Returns:
      True upon successful modification, otherwise an errno code is
      returned.
    '''

    self._debug('opcode: utime | path: %s' % path)

    try:
      return os.utime(tsumufs.nfsMountPoint + path, times)
    except OSError, e:
      self._debug('utime: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def access(self, path, mode):
    '''
    Test for access to a path.

    Returns:
      True upon successful check, otherwise an errno code is
      returned.
    '''

    self._debug('opcode: access | path: %s | mode: %o' % (path, mode))

    try:
      if not tsumufs.cacheManager.access(path, mode):
        return -errno.EACCES
    except OSError, e:
      self._debug('access: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  def statfs(self):
    '''
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
    '''
    self._debug('opcode: statfs')

    try:
      if tsumufs.nfsAvailable.isSet():
        return os.statvfs(tsumufs.nfsMountPoint)
      else:
        return os.statvfs(tsumufs.cacheBaseDir)
    except OSError, e:
      self._debug('statfs: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno
