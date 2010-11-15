#!/usr/bin/python
# Copyright (C) Jelmer Vernooij <jelmer@samba.org> 2010
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
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

import testtools
from buildfarm.web import build_link


class BuildLinkTests(testtools.TestCase):

    def test_build_link_no_rev(self):
        self.assertEquals("<a href='myself?function=View+Build;host=charis;tree=tdb;compiler=gcc'>status</a>", build_link("myself", "tdb", "charis", "gcc", None, "status"))


    def test_build_link_rev(self):
        self.assertEquals("<a href='myself?function=View+Build;host=charis;tree=tdb;compiler=gcc;revision=42'>status</a>", build_link("myself", "tdb", "charis", "gcc", "42", "status"))
