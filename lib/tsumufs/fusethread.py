# Copyright (C) 2008  Google, Inc. All Rights Reserved.
# Copyright (C) 2012  Michael Bryant.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

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

import logging
logger = logging.getLogger(__name__)

import fuse
from fuse import Fuse

import tsumufs
from extendedattributes import extendedattribute
from metrics import benchmark


class FuseThread(Fuse):
  '''
  Class that implements the prototype design of the TsumuFS
  filesystem. This class provides the main interface to Fuse. Note
  that this class is not a thread, yet it is considered as one in the
  design docs.
  '''

  def __init__(self, *args, **kw):
    '''
    Initializer. Prepares the object for initial use.
    '''

    Fuse.__init__(self, *args, **kw)
    self.multithreaded = 1

  def fsinit(self):
    '''
    Method callback that is called when FUSE's initial startup has
    completed, and the initialization of our client filesystem should
    start.

    Basic setup is done in here, such as instanciation of new objects
    and the startup of threads.
    '''

    logger.debug('Initializing cachemanager object.')
    try:
      tsumufs.cacheManager = tsumufs.CacheManager()
    except:
      logger.debug('Exception: %s' % traceback.format_exc())
      return False

    logger.debug('Initializing permissions overlay object.')
    try:
      tsumufs.permsOverlay = tsumufs.PermissionsOverlay()
    except:
      exc_info = sys.exc_info()

      logger.debug('*** Unhandled exception occurred')
      logger.debug('***     Type: %s' % str(exc_info[0]))
      logger.debug('***    Value: %s' % str(exc_info[1]))
      logger.debug('*** Traceback:')

      for line in traceback.extract_tb(exc_info[2]):
        logger.debug('***    %s(%d) in %s: %s' % line)

      return False

    # Setup the NFSMount object for both sync and mount threads to
    # access raw NFS with.
    logger.debug('Initializing nfsMount proxy.')
    try:
      tsumufs.nfsMount = tsumufs.NFSMount()
    except:
      # TODO(jtg): Erm... WHY can't we call tsumufs.syslogExceptHook here? O.o
      exc_info = sys.exc_info()

      logger.debug('*** Unhandled exception occurred')
      logger.debug('***     Type: %s' % str(exc_info[0]))
      logger.debug('***    Value: %s' % str(exc_info[1]))
      logger.debug('*** Traceback:')

      for line in traceback.extract_tb(exc_info[2]):
        logger.debug('***    %s(%d) in %s: %s' % line)

      return False

    # Initialize our threads
    logger.debug('Initializing sync thread.')
    try:
      self._syncThread = tsumufs.SyncThread()
    except:
      # TODO(jtg): Same as above... We should really fix this.
      exc_info = sys.exc_info()

      logger.debug('*** Unhandled exception occurred')
      logger.debug('***     Type: %s' % str(exc_info[0]))
      logger.debug('***    Value: %s' % str(exc_info[1]))
      logger.debug('*** Traceback:')

      for line in traceback.extract_tb(exc_info[2]):
        logger.debug('***    %s(%d) in %s: %s' % line)

      return False

    # Start the threads
    logger.debug('Starting sync thread.')
    self._syncThread.start()

    logger.debug('fsinit complete.')

  def main(self, args=None):
    '''
    Mainline of the FUSE client filesystem. This directly overrides
    the Fuse.main() method to allow us to manually shutdown things
    after the FUSE event loop has finished.
    '''

    class FuseFileWrapper(tsumufs.FuseFile):
      '''
      Inner class to wrap the FuseFile class with the reference to this thread,
      allowing us to get at the GetContext() call. Essentially we're creating a
      closure here. Ugly, but it's the only way to get the uid and gid into the
      FuseFile thread.

      Idea borrowed directly from Robie Basak in his email to fuse-dev, which is
      visible at <http://www.nabble.com/Python%3A-Pass-parameters-to-file_class-to18301066.html#a20066429>.
      '''

      def __init__(self2, *args, **kwargs):
        kwargs.update(self.GetContext())
        tsumufs.FuseFile.__init__(self2, *args, **kwargs)

    self.file_class = FuseFileWrapper

    result = Fuse.main(self, args)
    logger.debug('Fuse main event loop exited.')

    logger.debug('Setting event and condition states.')
    tsumufs.unmounted.set()
    tsumufs.nfsAvailable.clear()
    tsumufs.syncPause.clear()

    logger.debug('Waiting for the sync thread to finish.')
    self._syncThread.join()

    logger.debug('Shutdown complete.')

    return result

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
      tsumufs.mountPoint = os.path.join(os.getcwd(), tsumufs.mountPoint)

    # Shove the proper mountPoint into FUSE's mouth.
    self.fuse_args.mountpoint = tsumufs.mountPoint

    # Finally, calculate the runtime paths if they weren't specified already.
    if tsumufs.nfsMountPoint == None:
      tsumufs.nfsMountPoint = os.path.join(tsumufs.nfsBaseDir,
                                           tsumufs.mountPoint.replace('/', '-'))

    if tsumufs.cachePoint == None:
      tsumufs.cachePoint = os.path.join(tsumufs.cacheBaseDir,
                                        tsumufs.mountPoint.replace('/', '-'),
                                        'cache')

    tsumufs.synclogPath = os.path.abspath(os.path.join(tsumufs.cachePoint,
                                                       '../sync.log'))

    tsumufs.permsPath = os.path.abspath(os.path.join(tsumufs.cachePoint,
                                                     '../permissions.ovr'))

    logger.debug('mountPoint is %s' % tsumufs.mountPoint)
    logger.debug('nfsMountPoint is %s' % tsumufs.nfsMountPoint)
    logger.debug('cacheBaseDir is %s' % tsumufs.cacheBaseDir)
    logger.debug('cachePoint is %s' % tsumufs.cachePoint)
    logger.debug('synclogPath is %s' % tsumufs.synclogPath)
    logger.debug('permsPath is %s' % tsumufs.permsPath)
    logger.debug('mountOptions is %s' % tsumufs.mountOptions)


  ######################################################################
  # Filesystem operations and system calls below here

  @benchmark
  def getattr(self, path):
    '''
    Callback which is called into when a stat() is performed on the
    user side of things.

    Returns:
      A stat result object, the same as an os.lstat() call.

    Raises:
      None
    '''

    logger.debug('opcode: getattr (%d) | self: %s | path: %s' % (self.GetContext()['pid'], repr(self), path))

    try:
      result = tsumufs.cacheManager.statFile(path)
      logger.debug('Returning (%d, %d, %o)' %
                  (result.st_uid, result.st_gid, result.st_mode))

      return result

    except OSError, e:
      logger.debug('getattr: Caught OSError: %d: %s'
                  % (e.errno, e.strerror))
      raise

    except Exception, e:
      exc_info = sys.exc_info()

      logger.debug('*** Unhandled exception occurred')
      logger.debug('***     Type: %s' % str(exc_info[0]))
      logger.debug('***    Value: %s' % str(exc_info[1]))
      logger.debug('*** Traceback:')

      for line in traceback.extract_tb(exc_info[2]):
        logger.debug('***    %s(%d) in %s: %s' % line)

  @benchmark
  def setxattr(self, path, name, value, size):
    '''
    Callback that is called into when a setxattr() call is
    performed. This sets the value of an extended attribute, if that
    attribute is non-readonly. If the attribute isn't a valid name, or
    is read-only, this method returns -errno.EOPNOTSUPP.

    Returns:
      None, or -EOPNOTSUPP on error.
    '''

    logger.debug(('opcode: setxattr | path: %s | name: %s | '
                 'value: %s | size: %d')
                % (path, name, value, size))

    mode = tsumufs.cacheManager.statFile(path).st_mode

    if path == '/':
      type_ = 'root'
    elif stat.S_ISDIR(mode):
      type_ = 'dir'
    else:
      type_ = 'file'

    try:
      return tsumufs.ExtendedAttributes.setXAttr(type_, path, name, value)
    except KeyError, e:
      return -errno.EOPNOTSUPP

  @benchmark
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

    logger.debug('opcode: getxattr | path: %s | name: %s | size: %d'
                % (path, name, size))

    name = name.lower()
    mode = tsumufs.cacheManager.statFile(path).st_mode

    if path == '/':
      type_ = 'root'
    elif stat.S_ISDIR(mode):
      type_ = 'dir'
    else:
      type_ = 'file'

    try:
      xattr = tsumufs.ExtendedAttributes.getXAttr(type_, path, name)
      logger.debug('Got %s from xattr callback.' % str(xattr))

      if size == 0:
        # Caller just wants the size of the value.
        return len(xattr)
      else:
        return xattr
    except KeyError, e:
      logger.debug('Request for extended attribute that is not present in the '
                  'dictionary: <%s, %s, %s>'
                  % (repr(type_), repr(path), repr(name)))
      return -errno.EOPNOTSUPP
    except Exception, e:
      logger.debug('*** Exception occurred: %s (%s)' % (str(e), e.__class__))
      return -errno.EINVAL

  @benchmark
  def listxattr(self, path, size):
    '''
    Callback method to list the names of valid extended attributes in
    a file.

    Returns:
      The number of variables available if size is 0.
      A list of key names if size > 0.
    '''

    logger.debug('opcode: listxattr | path: %s | size: %d'
                % (path, size))

    mode = tsumufs.cacheManager.statFile(path).st_mode

    if path == '/':
      type_ = 'root'
    elif stat.S_ISDIR(mode):
      type_ = 'dir'
    else:
      type_ = 'file'

    keys = tsumufs.ExtendedAttributes.getAllNames(type_)

    if size == 0:
      return len(''.join(keys)) + len(keys)

    return keys

  @benchmark
  def readlink(self, path):
    '''
    Reads the value of a symlink.

    Returns:
      The string representation of the file the symlink points to, or
      a negative errno code on error.
    '''

    logger.debug('opcode: readlink | path: %s' % path)

    try:
      context = self.GetContext()
      tsumufs.cacheManager.access(context['uid'], path, os.R_OK)

      retval = tsumufs.cacheManager.readLink(path)
      logger.debug('Returning: %s' % retval)
      return retval
    except OSError, e:
      logger.debug('readlink: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def readdir(self, path, offset):
    '''
    Generator callback that returns a fuse.Direntry object every time
    it is called. Similar to the C readdir() call.

    Returns:
      A generator that yields a fuse.Direntry object, or an errno
      code on error.
    '''

    logger.debug('opcode: readdir | path: %s | offset: %d' % (path, offset))

    try:
      context = self.GetContext()
      tsumufs.cacheManager.access(context['uid'], path, os.R_OK)

      for filename in tsumufs.cacheManager.getDirents(path):
        if filename in [ '.', '..' ]:
          dirent = fuse.Direntry(filename)
          dirent.type = stat.S_IFDIR
          dirent.offset = offset
        else:
          pathname = os.path.join(path, filename)
          stat_result = tsumufs.cacheManager.statFile(pathname)

          dirent        = fuse.Direntry(filename)
          dirent.type   = stat.S_IFMT(stat_result.st_mode)
          dirent.offset = offset

        yield dirent
    except OSError, e:
      logger.debug('readdir: Caught OSError on %s: errno %d: %s'
                  % (filename, e.errno, e.strerror))
      yield -e.errno

  @benchmark
  def unlink(self, path):
    '''
    Callback to unlink a file on disk.

    Returns:
      True on successful unlink, or an errno code on error.
    '''

    logger.debug('opcode: unlink | path: %s' % path)

    try:
      context = self.GetContext()
      tsumufs.cacheManager.access(context['uid'], os.path.dirname(path),
                                  os.W_OK)

      tsumufs.cacheManager.removeCachedFile(path)
      tsumufs.syncLog.addUnlink(path, 'file')

      return 0
    except OSError, e:
      logger.debug('unlink: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def rmdir(self, path):
    '''
    Removes a directory from disk.

    Returns:
      True on successful unlink, or errno code on error.
    '''

    logger.debug('opcode: rmdir | path: %s' % path)

    try:
      context = self.GetContext()
      tsumufs.cacheManager.access(context['uid'], path, os.W_OK)

      tsumufs.cacheManager.removeCachedFile(path)
      tsumufs.syncLog.addUnlink(path, 'dir')

      return 0
    except OSError, e:
      logger.debug('rmdir: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def symlink(self, src, dest):
    '''
    Creates a symlink pointing to src as a file called dest.

    Returns:
      True on successful link creation, or errno code on error.
    '''

    logger.debug('opcode: symlink | src: %s | dest:: %s' % (src, dest))

    try:
      context = self.GetContext()
      tsumufs.cacheManager.access(context['uid'], os.path.dirname(dest), os.W_OK | os.X_OK)

      tsumufs.cacheManager.makeSymlink(dest, src)
      tsumufs.syncLog.addNew('symlink', filename=dest)

      return True
    except OSError, e:
      logger.debug('symlink: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def rename(self, old, new):
    '''
    Renames a file from old to new, possibly changing it's path as
    well as its filename.

    Returns:
      True on successful rename, or errno code on error.
    '''

    logger.debug('opcode: rename | old: %s | new: %s' % (old, new))

    try:
      context = self.GetContext()

      # According to the rename(2) man page, EACCES is raised when:
      #
      #   Write permission is denied for the directory containing oldpath or
      #   newpath, or, search permission is denied for one of the directories in
      #   the path prefix of oldpath or newpath, or oldpath is a directory and
      #   does not allow write permission (needed to update the ..  entry).
      #
      # Otherwise the rename is allowed. It doesn't care about permissions on
      # the file itself.

      # So, do this:
      #  1. Stat old. If dir and not W_OK, EACCES
      #  2. Verify X_OK | W_OK on dirname(old) and dirname(new)

      old_stat = tsumufs.cacheManager.statFile(old)

      if stat.S_ISDIR(old_stat.st_mode):
        tsumufs.cacheManager.access(context['uid'], old, os.W_OK)

      tsumufs.cacheManager.access(context['uid'], os.path.dirname(old),
                                  os.X_OK | os.W_OK)
      tsumufs.cacheManager.access(context['uid'], os.path.dirname(new),
                                  os.X_OK | os.W_OK)

      tsumufs.cacheManager.rename(old, new)
      tsumufs.syncLog.addRename(old_stat.st_ino, old, new)

      return 0
    except OSError, e:
      logger.debug('rename: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def link(self, src, dest):
    '''
    Links a the dest filename to the inode number of the src
    filename.

    Returns:
      True on successful linking, or errno code on error.
    '''

    logger.debug('opcode: link | src: %s | dest: %s' % (src, dest))

    try:
      # TODO(jtg): Implement this!
      return -errno.EOPNOTSUPP
    except OSError, e:
      logger.debug('link: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def chmod(self, path, mode):
    '''
    Changes the mode of a file.

    Returns:
      True on successful mode change, or errno code on error.
    '''

    logger.debug('opcode: chmod | path: %s | mode: %o' % (path, mode))

    context = self.GetContext()
    file_stat = tsumufs.cacheManager.statFile(path)

    try:
      inode = tsumufs.NameToInodeMap.nameToInode(nfspath)
    except KeyError, e:
      try:
        inode = file_stat.st_ino
      except (IOError, OSError), e:
        inode = -1

    logger.debug('context: %s' % repr(context))
    logger.debug('file: uid=%d, gid=%d, mode=%o' %
                (file_stat.st_uid, file_stat.st_gid, file_stat.st_mode))

    if ((file_stat.st_uid != context['uid']) and
        (context['uid'] != 0)):
      logger.debug('chmod: user not owner, and user not root -- EPERM')
      return -errno.EPERM

    tsumufs.cacheManager.access(context['uid'],
                                os.path.dirname(path),
                                os.F_OK)

    try:
      logger.debug('chmod: access granted -- chmoding')
      tsumufs.cacheManager.chmod(path, mode)
      logger.debug('chmod: adding metadata change')
      tsumufs.syncLog.addMetadataChange(path, inode)

      return 0
    except OSError, e:
      logger.debug('chmod: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def chown(self, path, newuid, newgid):
    '''
    Change the owner and/or group of a file.

    Returns:
      True on successful change, otherwise errno code is returned.
    '''

    logger.debug('opcode: chown | path: %s | uid: %d | gid: %d' %
               (path, newuid, newgid))

    context = self.GetContext()
    file_stat = tsumufs.cacheManager.statFile(path)

    if context['uid'] != 0:
      if newuid != -1:
        raise OSError(errno.EPERM)

      if (file_stat.st_uid != context['uid']) and (newgid != -1):
        if gid not in tsumufs.getGidsForUid(context['uid']):
          raise OSError(errno.EPERM)

    try:
      tsumufs.cacheManager.chown(path, newuid, newgid)
      tsumufs.syncLog.addMetadataChange(path, file_stat.st_ino)

      return 0
    except OSError, e:
      logger.debug('chown: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def truncate(self, path, size=0):
    '''
    Truncate a file to zero length.

    Returns:
      0 on successful truncation, otherwise an errno code is
      returned.
    '''

    logger.debug('opcode: truncate | path: %s | size: %d' %
               (path, size))

    try:
      fh = self.file_class(path, os.O_WRONLY)
      fh.ftruncate(size)
      fh.release(os.O_WRONLY)
      del fh

    except Exception, e:
      exc_info = sys.exc_info()

      logger.debug('*** Unhandled exception occurred')
      logger.debug('***     Type: %s' % str(exc_info[0]))
      logger.debug('***    Value: %s' % str(exc_info[1]))
      logger.debug('*** Traceback:')

      for line in traceback.extract_tb(exc_info[2]):
        logger.debug('***    %s(%d) in %s: %s' % line)

    return 0

  @benchmark
  def mknod(self, path, mode, dev):
    '''
    Creates a special device file with the sepcified mode and device
    number.

    Returns:
      True on successful creation, otherwise an errno code is
      returned.
    '''

    logger.debug('opcode: mknod | path: %s | mode: %d | dev: %s' %
               (path, mode, dev))

    context = self.GetContext()

    if mode & (stat.S_IFCHR | stat.S_IFBLK):
      if context['uid'] != 0:
        raise OSError(errno.EPERM)

    tsumufs.cacheManager.access(context['uid'], os.path.dirname(path), os.W_OK|os.X_OK)

    try:
      tsumufs.cacheManager.makeNode(path, mode, dev)

      if mode & stat.S_IFREG:
        tsumufs.syncLog.addNew('file', filename=path)
      elif mode & stat.S_IFCHR:
        tsumufs.syncLog.addNew('dev', filename=path, dev_type='char')
      elif mode & stat.S_IFBLK:
        tsumufs.syncLog.addNew('dev', filename=path, dev_type='block')
      elif mode & stat.S_IFIFO:
        tsumufs.syncLog.addNew('fifo', filename=path)

      return 0
    except OSError, e:
      logger.debug('mknod: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def mkdir(self, path, mode):
    '''
    Creates a new directory with the specified mode.

    Returns:
      0 on successful creation, othewrise a negative errno code is returned.
    '''

    logger.debug('opcode: mkdir | path: %s | mode: %o' % (path, mode))

    context = self.GetContext()
    tsumufs.cacheManager.access(context['uid'], os.path.dirname(path),
                                os.W_OK|os.X_OK)

    try:
      tsumufs.cacheManager.makeDir(path)
      tsumufs.permsOverlay.setPerms(path,
                                    context['uid'],
                                    context['gid'],
                                    mode | stat.S_IFDIR)
      tsumufs.syncLog.addNew('dir', filename=path)

      return 0

    except OSError, e:
      logger.debug('mkdir: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

    except Exception, e:
      exc_info = sys.exc_info()

      logger.debug('*** Unhandled exception occurred')
      logger.debug('***     Type: %s' % str(exc_info[0]))
      logger.debug('***    Value: %s' % str(exc_info[1]))
      logger.debug('*** Traceback:')

      for line in traceback.extract_tb(exc_info[2]):
        logger.debug('***    %s(%d) in %s: %s' % line)

      raise

  @benchmark
  def utime(self, path, times):
    '''
    Set the times (atime, mtime, and ctime) of a file.

    Returns:
      True upon successful modification, otherwise an errno code is
      returned.
    '''

    logger.debug('opcode: utime | path: %s' % path)

    try:
      result = tsumufs.cacheManager.stat(path, True)

      tsumufs.cacheManager.utime(path, times)
      tsumufs.syncLog.addMetadataChange(path, times=times)

      return True
    except OSError, e:
      logger.debug('utime: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
  def access(self, path, mode):
    '''
    Test for access to a path.

    Returns:
      True upon successful check, otherwise an errno code is
      returned.
    '''

    logger.debug('opcode: access | path: %s | mode: %o' % (path, mode))

    context = self.GetContext()
    logger.debug('uid: %s, gid: %s, pid: %s' %
                (repr(context['uid']),
                 repr(context['gid']),
                 repr(context['pid'])))

    try:
      tsumufs.cacheManager.access(context['uid'], path, mode)
      return 0
    except OSError, e:
      logger.debug('access: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno

  @benchmark
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
    logger.debug('opcode: statfs')

    try:
      if tsumufs.nfsAvailable.isSet():
        return os.statvfs(tsumufs.nfsMountPoint)
      else:
        return os.statvfs(tsumufs.cacheBaseDir)
    except OSError, e:
      logger.debug('statfs: Caught OSError: errno %d: %s'
                  % (e.errno, e.strerror))
      return -e.errno


@extendedattribute('root', 'tsumufs.version')
def xattr_version(type_, path, value=None):
  if not value:
    return '.'.join(map(str, tsumufs.__version__))

  return -errno.EOPNOTSUPP
