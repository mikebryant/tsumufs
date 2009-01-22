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

import glob
import sys
import os
import os.path

sys.path.append('lib')
import tsumufs

from distutils.core import setup

scripts = ['src/tsumufs']
scripts.extend(glob.glob(os.path.join('utils', '*')))

setup(name='TsumuFS',
      version='.'.join(map(str, tsumufs.__version__)),
      license='GPL v2',
      url='http://tsumufs.googlecode.com/',
      author_email='google-tsumufs@googlegroups.com',
      description='An NFS-based caching filesystem',

      package_dir={'': 'lib'},
      packages=['tsumufs'],
      scripts=['src/tsumufs',
               'utils/is-connected',
               'utils/gen-bug-report',
               'utils/in-cache',
               'utils/is-dirty',
               'utils/force-reconnect',
               'utils/force-disconnect',
               'utils/tsumufs-unmount-all']
      data_files=[('/usr/share/man/man1', glob.glob(os.path.join('man', '*')))],

      requires=['fuse', 'xattr']
      )
