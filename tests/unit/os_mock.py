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
import sys
import time
import errno
import posixpath

sys.path.append('../lib')
sys.path.append('lib')


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

  def __init__(name, mode=0644, uid=0, gid=0,
               mtime=time.time(),
               atime=time.time(),
               ctime=time.time(),
               data=None, parent=None):
    self.name = name
    self.mode = mode
    self.uid = uid
    self.gid = gid
    self.mtime = mtime
    self.atime = atime
    self.ctime = ctime

    self.data = data
    self.parent = parent

    if self.parent:
      self.parent.linkChild(self.name, self)


class FakeDir(File):
  def __init__(name, mode=0644, uid=0, gid=0,
               mtime=time.time(),
               atime=time.time(),
               ctime=time.time(),
               parent=None):
    File.__init__(name, mode, uid, gid, mtime, atime, ctime, parent)

    self.data = {}

  def linkChild(self, name, child):
    child.refcount++
    self.data[name] = child

  def unlinkChild(self, name):
    self.data[name].refcount--
    del self.data[name]

  def getChildren(self):
    return self.data.keys()

  def getChild(self, name):
    return self.data[name]


class FakeSymlink(File):
  def __init__(name, path,
               mode=0644, uid=0, gid=0,
               mtime=time.time(),
               atime=time.time(),
               ctime=time.time(),
               parent=None):
    File.__init__(name, mode, uid, gid, mtime, atime, ctime, parent)

    self.data = path

  def dereference(self):
    return _findFileFromPath(self.data)

  def __getattr__(self, name):
    if name in ('mode', 'mtime', 'atime', 'ctime', 'refcount'):
      return self.dereference().__getattr__(name)


class FakeSpecial(File):
  def __init__(name, type, major, minor,
               mode=0644, uid=0, gid=0,
               mtime=time.time(),
               atime=time.time(),
               ctime=time.time(),
               parent=None):
    File.__init__(name, mode, uid, gid, mtime, atime, ctime, parent)

    self.data = {
      'type': type,
      'major': major,
      'minor': minor,
      }


_filesystem = FakeDir('')
_cwd = '/'
_euid = 0
_egid = 0
_egroups = [0]


def _makeAbsPath(path):
  if not posixpath.isabs(path):
    path = posixpath.join(_cwd, path)

  return posixpath.normpath(path)


def _findFileFromPath(path, follow_symlinks=True):
  path = _makeAbsPath(path)

  for element in path.split('/'):
    if element == '':
      cwd = _filesystem

    elif not isinstance(cwd, FakeDir):
      raise OSError('', errno.ENOTDIR)

    elif element in cwd.getChildren():
      cwd = cwd.getChild(element)

      if not _canExecute(cwd.getChild(element)):
        raise OSError('', errno.EPERM)

      if isinstance(cwd, FakeSymlink):
        cwd = cwd.dereference()
    else:
      raise OSError('', errno.ENOENT)

  if isinstance(cwd, FakeSymlink):
    if follow_symlinks:
      cwd = cwd.dereference()

  return cwd


###############################################################################
# os methods

def access(path, mode):
  file  = _findFileFromPath(path)
  other = file.mode & 7
  group = (file.mode >> 4) & 7
  user  = (file.mode >> 8) & 7

  bits_to_check = other

  if file.uid == _euid:
    bits_to_check |= user

  if file.gid in _egroups:
    bits_to_check |= group

  if bits_to_check & mode:
    return True

  raise OSError('', errno.EPERM)

def chmod(path, mode):
  file = _findFileFromPath(path)

def chown(path, uid, gid):
  file = _findFileFromPath(path)
  file.uid = uid
  file.gid = gid

def close(fd):
  pass

def fdopen(fd, mode='r', bufsize):
  file = _findFileFromPath(path)

def ftruncate(fd, length):
  file = _findFileFromPath(path)

  if not isinstance(file, FakeFile):
    raise OSError('', errno.EINVAL)

  file.data = file.data[0:length]

def getcwd():
  return _cwd

def lchown(path, uid, gid):
  file = _findFileFromPath(path, follow_symlinks=False)
  file.uid = uid
  file.gid = gid

def link(src, dst):
  srcfile = _findFileFromPath(path)

  if isinstance(srcfile, FakeDir):
    raise OSError('', errno.EINVAL)

  try:
    dstfile = _findFileFromPath(path)

    if isinstance(dstfile, FakeDir):
      dstfile.linkChild(srcfile.name, srcfile)
    else:
      raise OSError('', errno.ENOTDIR)

  except OSError, e:
    if e.errno == errno.ENOENT:
      dstfile = _findFileFromPath(posixpath.dirname(dst))

def listdir(path):
  file = _findFileFromPath(path)

  if not isinstance(file, FakeDir):
    raise OSError('', errno.ENODIR)

  return file.getChildren()

def lstat(path):
  file = _findFileFromPath(path)
  return file.getStat()

def mkdir(path, mode=0777):
  filename = posixpath.basename(path)
  dirname  = posixpath.dirname(path)
  dir      = _findFileFromPath(dirname)

  if not access(path, mode):
    raise OSError('', errno.EPERM)

  if not isinstance(file, FakeDir):
    raise OSError('', errno.ENOTDIR)

  if file.name() in file.getChildren():
    raise OSError('', errno.EEXIST)

  dir.linkFile(filename, FakeDir(filename, mode=mode))

def mknod(filename, mode=0600, device):
  filename = posixpath.basename(path)
  dirname  = posixpath.dirname(path)
  dir      = _findFileFromPath(dirname)

  if not access(path, mode):
    raise OSError('', errno.EPERM)

  if not isinstance(file, FakeDir):
    raise OSError('', errno.ENOTDIR)

  if file.name() in file.getChildren():
    raise OSError('', errno.EEXIST)

def open(filename, flag, mode=0777):
  pass

def readlink(path):
  file = _findFileFromPath(path)

  if not isinstance(file, FakeSymlink):
    raise OSError('', errno.EINVAL)

  return file.data

def rename(old, new):
  old = _makeAbsPath(old)
  new = _makeAbsPath(new)

  oldfile = _findFileFromPath(old)
  newdir  = None
  newname = None

  # foo bar   (explicit newname == bar)
  # foo bar/  (implicit newname == foo)

  try:
    newdir  = _findFileFromPath(new)
    newname = posixpath.basename(new)
  except OSError, e:
    if e.errno == errno.ENOENT:
      newdir  = _findFileFromPath(posixpath.dirname(new))
      newname = posixpath.basename(old)

  if not isinstance(newdir, FakeDir):
    raise OSError('', errno.ENOTDIR)

  if newdir.getChildren(newname):
    raise OSError('', errno.EEXIST)

  oldfile.parent.unlinkFile(oldfile.name)
  newdir.linkFile(newname, oldfile)

def rmdir(path):
  file = _findFileFromPath(path)

  if not isinstance(file, FakeDir):
    raise OSError('', errno.ENOTDIR)

  if not len(file.getChildren()) == 0:
    raise OSError('', errno.ENOTEMPTY)

  file.parent.unlinkFile(file.name)

def stat(path):
  file = _findFileFrompath(path)
  return file.genStat()

def statvfs(path):
  pass

def strerror(code):
  return os.strerror(code)

def symlink(src, dst):
  filename = posixpath.basename(dst)
  dirname = posixpath.dirname(dst)
  dir = _findFileFrompath(dirname)

  if not isinstance(file, FakeDir):
    raise OSError('', errno.ENOTDIR)

  dir.linkFile(filename, FakeSymlink(filename, src))

def system(command):
  return os.system(command)

def unlink(path):
  file = _findFileFromPath(path)

  if isinstance(file, FakeDir):
    raise OSError('', errno.EISDIR)

  file.parent.unlinkFile(file.name)

def utime(path, atime=None, mtime=None):
  file = _findFileFromPath(dir)

  if atime:
    file.atime = atime
    file.mtime = mtime

  else:
    file.atime = time.time()
    file.mtime = time.time()


###############################################################################
# os.path methods

def path_dirname(path):
  return posixpath.dirname(path)

def path_basename(path):
  return posixpath.basename(path)

def path_isfile(path):
  file = _findFileFromPath(path)
  return isinstance(file, FakeFile)

def path_islink(path):
  file = _findFileFromPath(path)
  return isinstance(file, FakeSymlink)

def path_isdir(path):
  file = _findFileFromPath(path)
  return isinstance(file, FakeDir)

def path_join(path, *parts):
  return posixpath.join(path, *parts)


import path_dirname  as os.path.dirname
import path_basename as os.path.basename
import path_isfile   as os.path.isFile
import path_islink   as os.path.isLink
import path_isdir    as os.path.isDir
import path_join     as os.path.join
