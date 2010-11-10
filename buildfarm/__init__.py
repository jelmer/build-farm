#!/usr/bin/python
# Simple database query script for the buildfarm
#
# Copyright (C) Jelmer Vernooij <jelmer@samba.org>	   2010
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

import os


class BuildFarm(object):

    def __init__(self, path=None):
        if path is None:
            path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.path = path
        self.hostdb = self._open_hostdb()
        self.compilers = self._load_compilers()

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.path)

    def _open_hostdb(self):
        from buildfarm import hostdb
        return hostdb.HostDatabase(
            os.path.join(self.path, "hostdb.sqlite"))

    def _load_compilers(self):
        from buildfarm import util
        return util.load_list(os.path.join(self.webdir, "compilers.list"))
