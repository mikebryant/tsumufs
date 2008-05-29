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

import syslog

import tsumufs

class Debuggable(object):
  """
  This class implements a generic debuging method that all debuggable
  objects should use.
  """

  _syslogOpen = False
  _name = None

  def _setName(self, name):
    self._name = name

  def _validateName(self):
    if self._name == None:
      self._name = self.__class__

  def _getName(self):
    self._validateName()
    return self._name
  
  def _debug(self, args):
    """Quick method to output some debugging information which states the
    thread name a colon, and whatever arguments have been passed to
    it.

    Args:
      args: a list of additional arguments to pass, much like what
        print() takes.
    """
    
    self._validateName()

    if tsumufs.debugMode:
      if not self._syslogOpen:
        syslog.openlog(tsumufs.progName)

      s = "%s: %s" % (self._getName(), args)
      if len(s) > 252:
        s = s[:252] + "..."

      syslog.syslog(s)
