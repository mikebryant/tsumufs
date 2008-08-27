#!/usr/bin/python2.4
# -*- python -*-
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

'''Mock os module.'''

import os
import time
import errno
import posixpath
import stat

# Load in the os module into this namespace so vars defined exist for other code
# that includes this mock. (ie: O_CREAT)
from os import *

###############################################################################
# Helper objects to create the mock filesystem with

class FakeFile(object):
  name    = None
  mode    = 00644
  uid     = 0
  gid     = 0
  mtime   = time.time()
  atime   = time.time()
  ctime   = time.time()

  refcount = 0
  data     = None

  parent  = None

  def __init__(self, name, mode=00644, uid=0, gid=0,
               mtime=time.time(),
               atime=time.time(),
               ctime=time.time(),
               data=None, parent=None):

    self.uid = uid
    self.gid = gid

    self.mtime = mtime
    self.atime = atime
    self.ctime = ctime

    self.name = name
    self.mode = mode
    self.data = data
    self.parent = parent

    if self.parent:
      self.parent.linkChild(self.name, self)


class FakeDir(FakeFile):
  def __init__(self, name, mode=00755, uid=0, gid=0,
               mtime=time.time(),
               atime=time.time(),
               ctime=time.time(),
               parent=None):
    FakeFile.__init__(self, name, mode, uid, gid, mtime, atime, ctime, parent)

    self.data = {}

  def linkChild(self, name, child):
    child.refcount += 1
    self.data[name] = child
    child.parent = self

  def unlinkChild(self, name):
    self.data[name].refcount -= 1
    del self.data[name]

  def getChildren(self):
    return self.data.keys()

  def getChild(self, name):
    return self.data[name]


class FakeSymlink(FakeFile):
  def __init__(self, name, path,
               mode=00644, uid=0, gid=0,
               mtime=time.time(),
               atime=time.time(),
               ctime=time.time(),
               parent=None):
    FakeFile.__init__(self, name, mode, uid, gid, mtime, atime, ctime, parent)

    self.data = path

  def dereference(self):
    return _findFileFromPath(self.data)

  def __getattr__(self, name):
    if name in ('mode', 'mtime', 'atime', 'ctime', 'refcount'):
      return self.dereference().__getattr__(name)

    raise NameError()


class FakeFifo(FakeFile):
  pass


class FakeDevice(FakeFile):
  def __init__(self, name, type, major, minor,
               mode=00644, uid=0, gid=0,
               mtime=time.time(),
               atime=time.time(),
               ctime=time.time(),
               parent=None):
    FakeFile.__init__(self, name, mode, uid, gid, mtime, atime, ctime, parent)

    self.data = {
      'type': type,
      'major': major,
      'minor': minor,
      }


class FakeFileHandle(object):
  _filename = None
  _flags    = None
  _mode     = None

  def __init__(self, filename, flags, mode):
    pass


_filesystem = FakeDir('', mode=00755, )
_cwd = '/'
_euid = 0
_egid = 0
_egroups = [0]


def _canExecute(obj):
  # TODO: fix this to actually look at the permissions bits
  if isinstance(obj, FakeDir):
    return True
  else:
    return False


def _makeAbsPath(path):
  if not posixpath.isabs(path):
    path = posixpath.join(_cwd, path)

  return posixpath.normpath(path)


def _findFileFromPath(path, follow_symlinks=True):
  path = _makeAbsPath(path)
  cwd  = _filesystem

  # Walk the path to find the final element
  for element in path.split('/'):

    # Catch the root case and set our local cwd to the root.
    if element == '':
      cwd = _filesystem
      continue

    if not isinstance(cwd, FakeDir):
      raise OSError(errno.ENOTDIR, 'Not a directory' % path)

    if not _canExecute(cwd):
      raise OSError(errno.EPERM, 'Permission denied')

    if not element in cwd.getChildren():
      raise OSError(errno.ENOENT, 'File not found')

    cwd = cwd.getChild(element)

    # Dereference path elements only -- the last element should remain a symlink
    # if it is one.
    if (isinstance(cwd, FakeSymlink)
        and element != path.split('/')[-1]):
      cwd = cwd.dereference()

  return cwd


###############################################################################
# os methods

def access(path, mode):
  f     = _findFileFromPath(path)
  other = f.mode & 7
  group = (f.mode >> 4) & 7
  user  = (f.mode >> 8) & 7

  bits_to_check = other

  if f.uid == _euid:
    bits_to_check |= user

  if f.gid in _egroups:
    bits_to_check |= group

  if bits_to_check & mode:
    return True

  raise OSError(errno.EPERM, '')

def chmod(path, mode):
  f = _findFileFromPath(path)

def chown(path, uid, gid):
  f = _findFileFromPath(path)
  f.uid = uid
  f.gid = gid

def close(fd):
  pass

def fdopen(fd, mode='r', bufsize=None):
  # f = _findFileFromPath(fd)
  pass

def ftruncate(fd, length):
#   f = _findFileFromPath(path)

#   if not isinstance(f, FakeFile):
#     raise OSError(errno.EINVAL, '')

#   f.data = f.data[0:length]
  pass

def getcwd():
  return _cwd

def lchown(path, uid, gid):
  f = _findFileFromPath(path, follow_symlinks=False)
  f.uid = uid
  f.gid = gid

def link(src, dst):
  srcfile = _findFileFromPath(src)

  if isinstance(srcfile, FakeDir):
    raise OSError(errno.EINVAL, '')

  try:
    dstfile = _findFileFromPath(dst)

    if isinstance(dstfile, FakeDir):
      dstfile.linkChild(srcfile.name, srcfile)
    else:
      raise OSError(errno.ENOTDIR, '')

  except OSError, e:
    if e.errno == errno.ENOENT:
      dstfile = _findFileFromPath(posixpath.dirname(dst))

def listdir(path=''):
  f = _findFileFromPath(path)

  if not isinstance(f, FakeDir):
    raise OSError(errno.ENOTDIR, '')

  return f.getChildren()

def lstat(path):
  f = _findFileFromPath(path)
  return f.getStat()

def mkdir(path, mode=0777):
  filename = posixpath.basename(path)
  dirname  = posixpath.dirname(path)
  f        = _findFileFromPath(dirname)

  try:
    access(path, os.R_OK|os.W_OK|os.X_OK)
  except OSError, e:
    if e.errno != errno.ENOENT:
      raise

  if not isinstance(f, FakeDir):
    raise OSError(errno.ENOTDIR, '')

  if f.name in f.getChildren():
    raise OSError(errno.EEXIST, '')

  f.linkChild(filename, FakeDir(filename, mode=mode))

def makedev(major, minor):
  return { 'major': major, 'minor': minor }

def mknod(path, mode=None, device=None):
  # import stat explicitly here to fix a namespace issue.
  import stat

  if mode == None:
    mode = 00600 | stat.S_IFREG

  filename = posixpath.basename(path)
  dirname  = posixpath.dirname(path)
  destdir  = _findFileFromPath(dirname)

  access(posixpath.dirname(path), os.W_OK|os.X_OK)

  if not isinstance(destdir, FakeDir):
    raise OSError(errno.ENOTDIR, '')

  if filename in destdir.getChildren():
    raise OSError(errno.EEXIST, '')

  if mode & stat.S_IFREG:
    node = FakeFile(filename, mode)
  elif mode & stat.S_IFCHR:
    node = FakeDevice(filename, 'char', mode, device['major'], device['minor'])
  elif mode & stat.S_IFBLK:
    node = FakeDevice(filename, 'block', mode, device['major'], device['minor'])
  elif mode & stat.S_IFIFO:
    node = FakeFifo(filename, mode)
  else:
    raise OSError(errno.EINVAL, 'Invalid argument')

  destdir.linkChild(filename, node)

def open(filename, flag, mode=0777):
  pass

def readlink(path):
  f = _findFileFromPath(path)

  if not isinstance(f, FakeSymlink):
    raise OSError(errno.EINVAL, '')

  return f.data

def rename(old, new):
  old = _makeAbsPath(old)
  new = _makeAbsPath(new)

  # if the last element of the new path is a directory:
  #   alter new path to include the old basename
  try:
    if isinstance(_findFileFromPath(new), FakeDir):
      new = _makeAbsPath(new +'/'+ posixpath.basename(old))
  except OSError, e:
    if e.errno != errno.ENOENT:
      raise

  # if the last element of the new path is a file, unlink it and relink the old
  # path to the new.
  try:
    newfile = _findFileFromPath(new)

    if isinstance(newfile, FakeFile):
      newfile.parent.unlinkChild(newfile.name)
  except OSError, e:
    if e.errno != errno.ENOENT:
      raise

  oldfile = _findFileFromPath(old)
  newdir  = _findFileFromPath(posixpath.dirname(new))

  oldfile.parent.unlinkChild(oldfile.name)
  newdir.linkChild(posixpath.basename(new), oldfile)

def rmdir(path):
  f = _findFileFromPath(path)

  if not isinstance(f, FakeDir):
    raise OSError(errno.ENOTDIR, '')

  if not len(f.getChildren()) == 0:
    raise OSError(errno.ENOTEMPTY, '')

  f.parent.unlinkChild(f.name)

def stat(path):
  f = _findFileFromPath(path)
  return f.genStat()

def statvfs(path):
  pass

def strerror(code):
  return os.strerror(code)

def symlink(src, dst):
  filename = posixpath.basename(dst)
  dirname = posixpath.dirname(dst)
  f = _findFileFromPath(dirname)

  if not isinstance(f, FakeDir):
    raise OSError(errno.ENOTDIR, '')

  f.linkChild(filename, FakeSymlink(filename, src))

def system(command):
  return os.system(command)

def unlink(path):
  f = _findFileFromPath(path)

  if isinstance(f, FakeDir):
    raise OSError(errno.EISDIR, '')

  f.parent.unlinkChild(f.name)

def utime(path, atime=None, mtime=None):
  f = _findFileFromPath(dir)

  if atime:
    f.atime = atime
    f.mtime = mtime

  else:
    f.atime = time.time()
    f.mtime = time.time()
