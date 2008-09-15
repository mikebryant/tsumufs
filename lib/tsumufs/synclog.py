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
import errno
import cPickle

import tsumufs


class SyncConflictError(Exception):
  '''
  Class to represent a syncronization conflict.
  '''
  pass


class QueueValidationError(Exception):
  '''
  Class to represent a SyncLog queue validation error.
  '''
  pass

# syncqueue:
#  ( #<SyncItem{ type: 'new,
#      ftype: 'file|'dir|'socket|'fifo|'dev,
#      dtype: 'char|'block,
#      major: uint32,
#      minor: uint32,
#      filename: "..." },
#    { type: 'link,
#      inode: uint64,
#      filename: "..." },
#    { type: 'unlink,
#      filename: "..." },
#    { type: 'change,
#      inode: unit64 },
#    { type: 'rename,
#      old_fname: "...",
#      new_fname: "..." },
#    ... )


class SyncLog:
  '''
  Class that implements a queue for storing synclog entries in. Used
  primarily by the SyncThread class.
  '''

  _syncLogDir      = None
  _syncLogFilename = None
  _inodeChanges    = {}
  _syncQueue       = []
  _lock            = Lock()

  def __init__(self, logdir, logfilename='sync.log'):
    self._syncLogDir = logdir
    self._syncLogFilename = logfilename
    self.loadFromDisk()

  def loadFromDisk(self):
    '''
    Load the internal state of the SyncLog from disk and initialize
    the data structures.

    Raises:
      IOError: Some form of IO error while reading from the pickle
        file.
      PickleError: Error relating to the actual un-pickling of the
        data structures used internally.
    '''
    try:
      try:
        self._lock.acquire()
        filename = '%s/%s' % (self._syncLogDir, self._syncLogFilename)

        fp = open(filename, 'rb')
        try:
          data = cPickle.load(fp)
        finally:
          fp.close()

        self._inodeChanges = data['inodeChanges']
        self._syncQueue = data['syncQueue']
        self._inodeMap = data['inodeMap']
      except (IOError, OSError), e:
        if e.errno != errno.ENOENT:
          raise
        else:
          self._debug(('Unable to load synclog from disk -- %s/%s does not '
                       'exist.')
                      % (self._syncLogDir, self._syncLogFilename))
    finally:
      self._lock.release()

  def flushToDisk(self):
    '''
    Save the sync queue and inode hashes to disk.

    Run through each element in both queues and generate two lists of
    objects. Once the two lists have been generated, dump the lists to
    disk via the cPickle module.

    Queue files are stored on disk in the following python format:

    { inodeChanges: { <inum>: <InodeChange1>, ... ],
      syncQueue:   [ <SyncQueueItem1>, <SyncQueueItem2>, ... ] }

    Raises:
      IOError: An error relating to the attempt to write to a pickle
        file on disk.
      PickleError: Relates to the process of actually pickling the
        internal data structures.
    '''

    try:
      self._lock.acquire()
      filename = '%s/%s' % (self._syncLogDir, self._syncLogFilename)
      fp = open(filename, 'wb')
      cPickle.dump({ 'inodeChanges': self._inodeChanges,
                     'syncQueue': self._syncQueue,
                     'inodeMap': self._inodeMap}, fp)
    finally:
      fp.close()
      self._lock.release()

  def addNew(self, type, **params):
    '''
    Add a change for a new file to the queue.

    Args:
      type: A string of one one of the following: 'file', 'dir',
        'socket', 'fifo', or 'dev'.
      params: A hash of parameters used to complete the data
        structure. If type is set to 'dev', this structure must have
        the following members: dtype (set to one of 'char' or
        'block'), and major and minor, representing the major and minor
        numbers of the device being created.

    Raises:
      TypeError: When data passed in params is invalid or missing.
    '''
    self._lock.acquire()
    params['type'] = type
    syncitem = SyncQueueItem(params)
    self._syncQueue.unshift(syncitem)
    self._lock.release()

  def addLink(self, inum, filename):
    self._lock.acquire()
    syncitem = SyncQueueItem('link', inum=inum, filename=filename)
    self._syncQueue.unshift(syncitem)
    self._lock.release()

  def addUnlink(self, filename):
    self._lock.acquire()
    syncitem = SyncQueueItem('unlink', filename=filename)
    self._syncQueue.unshift(syncitem)
    self._lock.release()

  def addChange(self, inum, start, end, data):
    self._lock.acquire()
    syncitem = SyncQueueItem('change',
                             inum=inum,
                             start=start,
                             end=end,
                             data=data)
    self._syncQueue.unshift(syncitem)
    self._lock.release()

  def addRename(self, old, new):
    self._lock.acquire()
    syncitem = SyncQueueItem('rename', old=old, new=new)
    self._syncQueue.unshift(syncitem)
    self._lock.release()

  def popChange(self):
    self._lock.acquire()
    syncitem = self._syncQueue.shift()
    if syncitem.type == 'change':
      change = self._inodeChanges[syncitem.inum]
      del self._inodeChanges[syncitem.inum]
    else:
      change = None
      self._lock.release()
    return (syncitem, change)

# hash of inode changes:
#   { <inode number>: { data: ( { data: "...",
#                                 start: <start position>,
#                                 end: <end position>,
#                                 length: <length of data> },
#                               ... ),
#                       ctime: time_t uint64,
#                       mtime: time_t uint64,
#                       uid: uint32,
#                       gid: uint32,
#                       symlink_dest_path: "..." },
#     ... }

