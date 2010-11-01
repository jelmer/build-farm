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

import os
import shutil
import tempfile
import unittest

from buildfarm import data

class NonexistantTests(unittest.TestCase):

    def test_nonexistant(self):
        self.assertRaises(Exception, data.BuildfarmDatabase, "somedirthatdoesn'texist", None)


class BuildfarmDatabaseTests(unittest.TestCase):

    def setUp(self):
        super(BuildfarmDatabaseTests, self).setUp()

        self.path = tempfile.mkdtemp()

        for subdir in ["data", "cache", "web", "lcov", "lcov/data"]:
            os.mkdir(os.path.join(self.path, subdir))

        f = open(os.path.join(self.path, "web", "compilers.list"), "w")
        f.write("cc\n")
        f.close()

        f = open(os.path.join(self.path, "web", "hosts.list"), "w")
        f.write("gwenhwyvar\n")
        f.write("charis\n")
        f.close()

        self.x = data.BuildfarmDatabase(self.path)

    def test_build_fname(self):
        self.assertEquals(self.x.build_fname("mytree", "myhost", "cc"), "%s/data/upload/build.mytree.myhost.cc" % self.path)
        self.assertEquals(self.x.build_fname("mytree", "myhost", "cc", 123), "%s/data/oldrevs/build.mytree.myhost.cc-123" % self.path)

    def test_cache_fname(self):
        self.assertEquals(self.x.cache_fname("mytree", "myhost", "cc", 123), "%s/cache/build.mytree.myhost.cc-123" % self.path)
        self.assertEquals(self.x.cache_fname("mytree", "myhost", "cc"), "%s/cache/build.mytree.myhost.cc" % self.path)

    def tearDown(self):
        shutil.rmtree(self.path)
        super(BuildfarmDatabaseTests, self).tearDown()