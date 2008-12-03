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
import errno
import cPickle
import threading

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


class SyncLog(tsumufs.Debuggable):
  '''
  Class that implements a queue for storing synclog entries in. Used
  primarily by the SyncThread class.
  '''

  _inodeChanges    = {}
  _syncQueue       = []
  _lock            = threading.Lock()
  _checkpointer    = None

  def __init__(self):
    self._checkpointer = threading.Timer(tsumufs.checkpointTimeout,
                                         self.checkpoint)
    self._checkpointer.start()

  def __str__(self):
    inodechange_str = repr(self._inodeChanges)
    syncqueue_str   = repr(self._syncQueue)

    string = (('<SyncLog \n'
              '    _inodeChanges: %s\n'
              '    _syncQueue: %s\n'
              '>') % (inodechange_str,
                      syncqueue_str))

    return string

  def loadFromDisk(self):
    '''
    Load the internal state of the SyncLog from disk and initialize
    the data structures.

    Raises:
      OSError: Some form of OS error while reading from the pickle file.
      IOError: Some form of IO error while reading from the pickle file.
      PickleError: Error relating to the actual un-pickling of the
        data structures used internally.
    '''
    try:
      try:
        self._lock.acquire()

        fp = open(tsumufs.synclogPath, 'rb')
        try:
          data = cPickle.load(fp)
        finally:
          fp.close()

        self._inodeChanges = data['inodeChanges']
        self._syncQueue = data['syncQueue']
      except IOError, e:
        if e.errno != errno.ENOENT:
          raise
        else:
          self._debug(('Unable to load synclog from disk -- %s does not '
                       'exist.') % (tsumufs.synclogPath))
      except OSError, e:
        raise
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
      syncQueue:   [ <tsumufs.SyncItem1>, <tsumufs.SyncItem2>, ... ] }

    Raises:
      IOError: An error relating to the attempt to write to a pickle
        file on disk.
      PickleError: Relates to the process of actually pickling the
        internal data structures.
    '''

    try:
      self._lock.acquire()

      fp = open(tsumufs.synclogPath, 'wb')
      cPickle.dump({ 'inodeChanges': self._inodeChanges,
                     'syncQueue': self._syncQueue }, fp)
    finally:
      fp.close()
      self._lock.release()

  def isNewFile(self, fusepath):
    '''
    Check to see if fusepath is a file the user created locally.

    Returns:
      Boolean

    Raises:
      Nothing
    '''

    for change in self._syncQueue:
      if ((change.getType() == 'new') and
          (change.getFilename() == fusepath)):
        return True

    return False

  def isUnlinkedFile(self, fusepath):
    '''
    Check to see if fusepath is a file that was unlinked previously.

    Returns:
      Boolean

    Raises:
      Nothing
    '''

    is_unlinked = False

    for change in self._syncQueue:
      if change.getFilename() == fusepath:
        if change.getType() == 'unlink':
          is_unlinked = True
        else:
          is_unlinked = False

    return is_unlinked

  def addNew(self, type_, **params):
    '''
    Add a change for a new file to the queue.

    Args:
      type: A string of one one of the following: 'file', 'dir',
        'socket', 'fifo', or 'dev'.
      params: A hash of parameters used to complete the data
        structure. If type is set to 'dev', this structure must have
        the following members: dev_type (set to one of 'char' or
        'block'), and major and minor, representing the major and minor
        numbers of the device being created.

    Raises:
      TypeError: When data passed in params is invalid or missing.
    '''
    try:
      self._lock.acquire()

      params['file_type'] = type_
      syncitem = tsumufs.SyncItem('new', **params)

      self._syncQueue.append(syncitem)
    finally:
      self._lock.release()

  def checkpoint(self):
    self._debug('Checkpointing synclog...')

    self.flushToDisk()
    self._checkpointer = threading.Timer(tsumufs.checkpointTimeout,
                                         self.checkpoint)
    self._checkpointer.start()

    self._debug('...complete. Next checkpoint in %d seconds.'
                % tsumufs.checkpointTimeout)

  def addLink(self, inum, filename):
    try:
      self._lock.acquire()

      syncitem = tsumufs.SyncItem('link', inum=inum, filename=filename)
      self._syncQueue.append(syncitem)
    finally:
      self._lock.release()

  def addUnlink(self, filename):
    '''
    Add a change to unlink a file. Additionally removes all previous changes in
    the queue for that filename.

    Args:
      filename: the filename to unlink.

    Raises:
      Nothing.
    '''

    try:
      self._lock.acquire()

      # TODO(jtg): Make this check the dirty status of a file before doing a
      # walk of the queue. Walking the entire sync queue every unlink() call is
      # expensive, even though it's O(n).

      # Walk the queue backwards (newest to oldest) and remove any changes
      # relating to this filename. We can mutate the list because going
      # backwards, index numbers don't change after deletion (IOW, we're always
      # deleting the tail).

      if self.isNewFile(filename):
        is_new_file = True
      else:
        is_new_file = False

      # Have to offset these by one because range doesn't function the same as
      # lists. *sigh*
      for index in range(len(self._syncQueue)-1, -1, -1):
        change = self._syncQueue[index]

        if change.getType() in ('new', 'change', 'link'):
          if change.getFilename() == filename:
            # Remove the change
            del self._syncQueue[index]

            # Remove any inodeChanges associated with this filename.
            if (change.getInum() != None and
                self._inodeChanges.has_key(change.getInum())):
              del self._inodeChanges[change.getInum()]

        if change.getType() in ('rename'):
          if change.getNewFilename() == filename:
            # Okay, follow the rename back to remove previous changes. Leave the
            # rename in place because the destination filename is a change we
            # want to keep.
            filename = change.getOldFilename()

            # TODO(jtg): Do we really need to keep these renames? Unlinking the
            # final destination filename in the line of renames is akin to just
            # unlinking the original file in the first place. Ie:
            #
            #      file -> file' -> file'' -> unlinked
            #
            # After each successive rename, the previous file ceases to
            # exist. Once the final unlink is called, the previous sucessive
            # names no longer matter. Technically we could replace all of the
            # renames with a single unlink of the original filename and achieve
            # the same result.

      # Now add an additional syncitem to the queue to represent the unlink if
      # it wasn't a file that was created on the cache by the user.
      if not is_new_file:
        syncitem = tsumufs.SyncItem('unlink', filename=filename)
        self._syncQueue.append(syncitem)

    finally:
      self._lock.release()

  def addChange(self, fname, inum, start, end, data):
    try:
      self._lock.acquire()

      if self._inodeChanges.has_key(inum):
        # Don't need to add a syncitem because it's already there.
        inodechange = self._inodeChanges[inum]
      else:
        syncitem = tsumufs.SyncItem('change', filename=fname, inum=inum)
        self._syncQueue.append(syncitem)

        inodechange = tsumufs.InodeChange()

        # Grab the data length initially so we can manage truncate calls.
        datalength = tsumufs.cacheManager.statFile(fname).st_size
        inodechange.setDataLength(datalength)

        self._inodeChanges[inum] = inodechange

      inodechange.addDataChange(start, end, data)
    finally:
      self._lock.release()

  def truncateChanges(self, fusepath, size):
    try:
      self._lock.acquire()

      for change in self._syncQueue:
        if ((change.getFilename() == fusepath) and
            (change.getType() == 'change')):
          if self._inodeChanges.has_key(change.getInum()):
            self._debug('Truncating data in %s' % repr(change))
            inodechange = self._inodeChanges[change.getInum()]
            inodechange.truncateLength(size)

    finally:
      self._lock.release()

  def addRename(self, old, new):
    try:
      self._lock.acquire()

      syncitem = tsumufs.SyncItem('rename', old=old, new=new)
      self._syncQueue.append(syncitem)
    finally:
      self._lock.release()

  def popChange(self):
    try:
      self._lock.acquire()

      syncitem = self._syncQueue.pop()

      if syncitem.type == 'change':
        change = self._inodeChanges[syncitem.inum]
        del self._inodeChanges[syncitem.inum]
      else:
        change = None

      return (syncitem, change)
    finally:
      self._lock.release()

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

