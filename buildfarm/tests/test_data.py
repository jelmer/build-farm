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
import time
import unittest

from buildfarm import data

from buildfarm.tests import BuildFarmTestCase


class NonexistantTests(unittest.TestCase):

    def test_nonexistant(self):
        self.assertRaises(
            Exception, data.BuildResultStore, "somedirthatdoesn'texist", None)


class BuildResultStoreTests(BuildFarmTestCase):

    def setUp(self):
        super(BuildResultStoreTests, self).setUp()

        self.write_compilers(["cc"])
        self.write_hosts(["gwenhwyvar", "charis"])
        self.write_trees({"tdb": {"scm": "git", "repo": "tdb", "branch": "master"}})

        self.x = data.BuildResultStore(self.path)

    def test_build_fname(self):
        self.assertEquals(
            self.x.build_fname("mytree", "myhost", "cc"),
            "%s/data/upload/build.mytree.myhost.cc" % self.path)
        self.assertEquals(
            self.x.build_fname("mytree", "myhost", "cc", 123),
            "%s/data/oldrevs/build.mytree.myhost.cc-123" % self.path)

    def test_cache_fname(self):
        self.assertEquals(
            self.x.cache_fname("mytree", "myhost", "cc", 123),
            "%s/cache/build.mytree.myhost.cc-123" % self.path)
        self.assertEquals(
            self.x.cache_fname("mytree", "myhost", "cc"),
            "%s/cache/build.mytree.myhost.cc" % self.path)

    def test_build_age_mtime(self):
        path = self.create_mock_logfile("tdb", "charis", "cc")
        # Set mtime to something in the past
        os.utime(path, (time.time(), time.time() - 990))
        build = self.x.get_build("tdb", "charis", "cc")
        age = build.age_mtime()
        self.assertTrue(age >= 990 and age <= 1000, "age was %d" % age)

    def test_get_build_nonexistant(self):
        self.assertRaises(data.NoSuchBuildError, self.x.get_build, "tdb",
            "charis", "cc")

    def test_build_age_ctime(self):
        path = self.create_mock_logfile("tdb", "charis", "cc")
        # Set mtime to something in the past
        build = self.x.get_build("tdb", "charis", "cc")
        age = build.age_ctime()
        self.assertTrue(age >= 0 and age <= 10, "age was %d" % age)

    def test_read_log(self):
        path = self.create_mock_logfile("tdb", "charis", "cc",
            contents="This is what a log file looks like.")
        build = self.x.get_build("tdb", "charis", "cc")
        self.assertEquals("This is what a log file looks like.", build.read_log())

    def test_read_err(self):
        self.create_mock_logfile("tdb", "charis", "cc")
        path = self.create_mock_logfile("tdb", "charis", "cc",
            kind="stderr",
            contents="This is what an stderr file looks like.")
        build = self.x.get_build("tdb", "charis", "cc")
        self.assertEquals("This is what an stderr file looks like.", build.read_err())
